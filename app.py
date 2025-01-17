import sys
import json
from datetime import datetime
import threading
import time

from flask import Flask, render_template, request, redirect, jsonify, url_for, flash, Response, session, current_app
import plotly.graph_objs as go
import plotly.express as px
import plotly.io as pio
import math
from plotly.subplots import make_subplots
from plotly import utils
from utils import *

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Add this line for flash messages

fetch_complete = threading.Event()

def load_salary_data():
    with open('salary_map.json', 'r') as f:
        return json.load(f)

def get_available_years():
    """Get list of years available in the database"""
    con = get_connection()
    query = """
    SELECT DISTINCT date_part('year', date) as year
    FROM transactions
    ORDER BY year DESC
    """
    years = [int(row[0]) for row in con.execute(query).fetchall()]
    con.close()
    return years

def create_sankey_diagram(year):
    """Create Sankey diagram of income and spending"""
    salary, spend_data = get_sankey_data(year)
    
    # Prepare Sankey data
    labels = ['Income']  # Start with Income node
    source = []  # Source nodes
    target = []  # Target nodes
    value = []   # Values for flows
    
    # Add category nodes
    for i, (category, amount) in enumerate(spend_data, 1):
        labels.append(category)
        source.append(0)  # From Income (node 0)
        target.append(i)  # To category node
        value.append(float(amount))
    
    # Calculate remaining/savings
    total_spend = sum(float(amount) for _, amount in spend_data)
    if salary > total_spend:
        labels.append('Savings')
        source.append(0)
        target.append(len(labels) - 1)
        value.append(salary - total_spend)

    # Create Sankey diagram
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=labels,
            color="blue"
        ),
        link=dict(
            source=source,
            target=target,
            value=value
        )
    )])

    fig.update_layout(
        title_text=f"Income and Spending Flow {year}",
        font_size=12,
        height=600
    )

    # Change here: include plotlyjs for AJAX updates
    return fig.to_html(full_html=False, include_plotlyjs=True)

def create_budget_tracker():
    """Create budget tracking visualization for current month"""
    current_spend = get_current_month_spend_by_category()
    budget_limits = load_budget_data()
    
    categories = []
    spend_amounts = []
    remaining_amounts = []
    colors = []
    budget_text = []  # For showing total budget
    spent_text = []   # For showing amount spent
    
    for category, budget in budget_limits.items():
        if category not in ['Housing', 'Utilities']:
            spent = current_spend.get(category, 0)
            remaining = max(budget - spent, 0)
            over_budget = spent > budget
            
            categories.append(category)
            spend_amounts.append(spent)
            remaining_amounts.append(remaining if not over_budget else 0)
            colors.append('red' if over_budget else 'blue')
            
            # Create text labels
            budget_text.append(f"Budget: ${budget:,.0f}")  # Total budget at top
            if over_budget:
                spent_text.append(f"${spent:,.0f}<br>Over by: ${spent - budget:,.0f}")
            else:
                spent_text.append(f"${spent:,.0f}")
    
    # Create stacked bar chart
    fig = go.Figure(data=[
        go.Bar(
            name='Spent',
            x=categories,
            y=spend_amounts,
            marker_color=colors,
            text=spent_text,
            textposition='auto',
            hovertemplate='%{x}<br>Spent: $%{y:,.2f}<extra></extra>'
        ),
        go.Bar(
            name='Remaining',
            x=categories,
            y=remaining_amounts,
            marker_color='lightgray',
            text=budget_text,
            textposition='outside',
            textfont=dict(color='black'),
            hovertemplate='%{x}<br>Remaining: $%{y:,.2f}<extra></extra>'
        )
    ])
    
    # Update layout with increased height
    fig.update_layout(
        title=f"Budget Tracking - {datetime.now().strftime('%B %Y')}",
        barmode='stack',
        height=600,  # Increased from 400 to 600
        yaxis_title="Amount ($)",
        xaxis_title="Category",
        xaxis_tickangle=-45,
        showlegend=True,
        # Add more space at the top for labels
        yaxis=dict(
            range=[0, max([a + b for a, b in zip(spend_amounts, remaining_amounts)]) * 1.15]
        )
    )

    return fig.to_html(full_html=False, include_plotlyjs=False)

@app.route('/')
def index():
    graphs = []

    # Get summary statistics
    current_year = datetime.now().year
    current_year_stats = get_current_year_stats(current_year)
    previous_years_avg = get_previous_years_avg(current_year)
    category_spend = get_category_spend(current_year)
    category_spend_avg = get_category_spend_avg(current_year)
    top_monthly_subscriptions = get_top_monthly_subscriptions(current_year)

    # Calculate percentage differences and trends
    category_spend_comparison = {}
    for category, current in category_spend.items():
        avg = category_spend_avg.get(category, 0)
        if avg > 0:
            percentage = ((current - avg) / avg) * 100
            trend = 'up' if current > avg else 'down'
        else:
            percentage = 100
            trend = 'up'
        category_spend_comparison[category] = {
            'current': current,
            'avg': avg,
            'percentage': percentage,
            'trend': trend
        }

    # Format dollar amounts and round to nearest integer
    if current_year_stats['total_spend'] is None:
        pass
    else:
        current_year_stats['total_spend'] = f"{round(current_year_stats['total_spend']):,}"
        current_year_stats['avg_transaction'] = f"{round(current_year_stats['avg_transaction']):,}"
        current_year_stats['max_transaction'] = f"{round(current_year_stats['max_transaction']):,}"

    previous_years_avg['avg_yearly_spend'] = f"{round(previous_years_avg['avg_yearly_spend']):,}"
    previous_years_avg['avg_transaction'] = f"{round(previous_years_avg['avg_transaction']):,}"
    previous_years_avg['avg_max_transaction'] = f"{round(previous_years_avg['avg_max_transaction']):,}"

    for category, data in category_spend_comparison.items():
        data['current'] = f"{round(float(data['current'])):,}"
        data['avg'] = f"{round(float(data['avg'])):,}"
        data['percentage'] = round(data['percentage'])

    # Round the values in top_monthly_subscriptions
    top_monthly_subscriptions = [(desc, round(amount), count) for desc, amount, count in top_monthly_subscriptions]

    ### ------------ create monthly spend chart ----
    data = query_monthly_spend()
    if not data:
        return "<h2>No monthly data available.</h2>"

    months = [record[0].strftime('%Y-%m') for record in data]
    totals = [record[1] for record in data]

    fig = go.Figure(data=[
        go.Bar(
            x=months,
            y=totals,
            text=totals,
            texttemplate='%{text:$.0f}',
            textposition="outside",
            textfont=dict(color="black"),
            hovertemplate='Month: %{x}<br>Total: $%{y:,.2f}<br>Click for details',
            customdata=months  # This now contains the full 'YYYY-MM' string
        )
    ])
    fig.update_layout(
        title='Monthly Spend Overview',
        xaxis_title='Month',
        yaxis_title='Total Spend ($)',
        height=600
    )

    # Convert plotly figure to JSON for rendering
    graph_monthly = fig.to_html(full_html=False, include_plotlyjs=False, config={'displayModeBar': False})
    graphs.append(graph_monthly)

    ### ------------ create yearly spend chart ----
    data = query_yearly_spend()
    if not data:
        return "<h2>No yearly data available.</h2>"

    years = [record[0].strftime('%Y') for record in data]
    totals = [record[1] for record in data]

    # Load salary data
    salary_data = load_salary_data()

    # Calculate spend percentages
    spend_percentages = []
    for year, total in zip(years, totals):
        if year in salary_data and salary_data[year] > 0:
            percentage = (total / salary_data[year]) * 100
        else:
            percentage = 0
        spend_percentages.append(percentage)

    # Create the figure with two subplots and shared x-axis
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=('Yearly Spend Overview', 'Spend % of Salary'))

    # Add spend line to the first subplot
    fig.add_trace(
        go.Scatter(
            x=years,
            y=totals,
            mode="lines+markers+text",
            name="Total Spend",
            text=totals,
            textposition='top center',
            texttemplate='%{text:$,.0f}',
            textfont=dict(color="blue"),
            line=dict(color='blue', width=2),
            marker=dict(size=8, color='blue')
        ),
        row=1, col=1
    )

    # Add spend percentage line to the second subplot
    fig.add_trace(
        go.Scatter(
            x=years,
            y=spend_percentages,
            mode="lines+markers+text",
            name="Spend % of Salary",
            text=spend_percentages,
            textposition='top center',
            texttemplate='%{text:.1f}%',
            textfont=dict(color="red"),
            line=dict(color='red', width=2),
            marker=dict(size=8, color='red')
        ),
        row=2, col=1
    )

    # Update layout
    fig.update_layout(
        height=800,  # Increase overall height
        showlegend=False,
        title_text='Yearly Spend Overview and Percentage of Salary'
    )

    # Update y-axes titles
    fig.update_yaxes(title_text="Total Spend ($)", row=1, col=1)
    fig.update_yaxes(title_text="Spend % of Salary", row=2, col=1)

    # Update x-axis
    fig.update_xaxes(title_text="Year", row=2, col=1)

    # Convert plotly figure to JSON for rendering
    graph_yearly = fig.to_html(full_html=False)
    graphs.append(graph_yearly)

    ### ------------ create heatmap for category spending over time ----
    df = query_yearly_spend_by_cat()
    if df.empty:
        return "<h2>No yearly cat data available.</h2>"

    df_pivot = df.pivot(index='category', columns='year', values='total_amount')

    # Prepare data for heatmap
    x = df_pivot.index.tolist()
    y = df_pivot.columns.tolist()
    z = df_pivot.values.T.tolist()

    # Create the heatmap
    fig_heatmap = go.Figure(data=go.Heatmap(
        z=z,
        x=x,
        y=y,
        colorscale='Blues',
        hoverongaps=False
    ))

    # Update layout
    fig_heatmap.update_layout(
        title="Category Spending Heatmap",
        xaxis_title="Category",
        yaxis_title="Year",
        height=600,
        xaxis=dict(tickangle=-45),
        yaxis=dict(
            tickmode='array',
            tickvals=y,
            ticktext=[str(int(year)) for year in y]
        )
    )

    # Add text annotations
    annotations = []
    for i, year in enumerate(y):
        for j, category in enumerate(x):
            value = z[i][j]
            annotations.append(dict(
                x=category,
                y=year,
                text=f"${value:,.0f}",
                showarrow=False,
                font=dict(color="white" if value > df_pivot.values.max() / 2 else "black")
            ))

    fig_heatmap.update_layout(annotations=annotations)

    graph_heatmap = fig_heatmap.to_html(full_html=False, include_plotlyjs=False)
    graphs.append(graph_heatmap)

    # Get available years for dropdown
    available_years = get_available_years()
    
    # Add budget tracker before the Sankey diagram
    graph_budget = create_budget_tracker()
    graphs.append(graph_budget)
    
    # Create Sankey diagram with current year
    graph_sankey = create_sankey_diagram(current_year)
    graphs.append(graph_sankey)

    print(f"Number of graphs: {len(graphs)}")  # Print the number of graphs

    return render_template('index.html', 
                           graphs=graphs, 
                           current_year_stats=current_year_stats, 
                           previous_years_avg=previous_years_avg,
                           category_spend=category_spend_comparison,
                           current_year=current_year,
                           available_years=available_years,
                           top_monthly_subscriptions=top_monthly_subscriptions)

# Route to handle the form submission and update DuckDB
@app.route('/update', methods=['POST'])
def update():
    con = get_connection()

    # Get the row count to loop through form fields
    row_count = int(request.form['row_count'])
    print(row_count)
    # Track the number of rows updated
    rows_updated = 0

    # Loop through each row and extract the corresponding data
    for i in range(row_count):
        date = request.form[f'date_{i}']
        amount = request.form[f'amount_{i}']
        description = request.form[f'description_{i}']
        category = request.form[f'category_{i}']
        notes = request.form[f'notes_{i}']

        # Update DuckDB with the new values
        query = """
        UPDATE transactions 
        SET category = ?, amount = ?, notes = ?
        WHERE date = ? AND description = ?
        """
        try:
            result = con.execute(query, [category, amount, notes, date, description])
            rows_updated += result.rowcount  # Track how many rows were updated
        except Exception as e:
            print(f'Error updating row: {e}')

    # Explicitly commit changes
    con.commit()
    con.close()

    print(f"Rows updated: {rows_updated}")
    flash(f"{rows_updated} transactions updated successfully", "success")
    return redirect(url_for('update_form'))

@app.route('/update_form')
def update_form():
    con = get_connection()
    df = con.execute("SELECT * FROM transactions WHERE category = 'Uncategorized' AND (Notes IS NULL OR Notes = 'None') ORDER BY date desc ").fetchdf()
    con.close()
    categories = load_categories()
    return render_template('update.html', data=df, categories=categories)

@app.route('/insert', methods=['GET'])
def insert_form():
    categories = load_categories()
    return render_template('insert.html', categories=categories)

# Add this new route to handle AJAX requests for top transactions
@app.route('/top_transactions/<year_month>')
def top_transactions(year_month):
    top_transactions = query_top_transactions_for_month(year_month)
    print(f"Top transactions for {year_month}:", top_transactions)  # Add this line
    return jsonify(top_transactions)

@app.route('/fetch_emails', methods=['POST'])
def fetch_emails():
    with app.app_context():
        fetch_and_process_emails()
    flash("Emails fetched successfully", "success")
    return redirect(url_for('update_form'))

def fetch_and_process_emails():
    try:
        service = authenticate_gmail()
        messages = fetch_unread_emails(service)

        # Load category mapping
        with open('category_mapping.json') as f:
            category_map = json.load(f)
        
        processed_count = 0
        for msg in messages:
            email_data = get_email_data(service, msg['id'])
            if email_data is not None:
                try:
                    store_data_in_duckdb(email_data, category_map)
                    mark_email_as_read(service, msg['id'])
                    processed_count += 1
                except Exception as e:
                    print(f"ERROR storing data: {e}")
        print(f"Email fetching and processing completed. Processed {processed_count} emails.")
        flash(f'Email fetching and processing completed. Processed {processed_count} emails.', 'success')
    except Exception as e:
        print(f"Error in fetch_and_process_emails: {e}")
        flash(f'Error in email fetching: {str(e)}', 'error')
    finally:
        fetch_complete.set()

@app.route('/fetch_status')
def fetch_status():
    def generate():
        while not fetch_complete.is_set():
            time.sleep(1)
            yield "data: waiting\n\n"
        if 'fetch_complete_message' in session:
            yield f"data: {session.pop('fetch_complete_message')}\n\n"
        else:
            yield "data: complete\n\n"
    return Response(generate(), mimetype='text/event-stream')

@app.route('/insert_transaction', methods=['POST'])
def insert_transaction():
    try:
        # Convert the datetime-local input to proper timestamp format
        raw_date = request.form['date']
        date = datetime.strptime(raw_date, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S')
        amount = float(request.form['amount'])
        description = request.form['description']
        category = request.form['category']
        notes = request.form.get('notes', '')

        # Validate category is in predefined list
        categories = load_categories()
        if category not in categories:
            raise ValueError('Invalid category selected')

        con = get_connection()
        query = """
        INSERT INTO transactions (date, amount, description, category, notes)
        VALUES (?, ?, ?, ?, ?)
        """
        con.execute(query, [date, amount, description, category, notes])
        con.commit()
        con.close()
        
        flash('Transaction added successfully!', 'success')
    except ValueError as ve:
        flash(f'Validation error: {str(ve)}', 'error')
    except Exception as e:
        flash(f'Error adding transaction: {str(e)}', 'error')
    
    return redirect(url_for('insert_form'))

@app.context_processor
def inject_current_year():
    return {"current_year": datetime.now().year}

@app.route('/update_sankey/<int:year>')
def update_sankey(year):
    """AJAX endpoint to get updated Sankey diagram"""
    return create_sankey_diagram(year)

if __name__ == '__main__':
    # Run Flask app
    app.run(debug=True)
