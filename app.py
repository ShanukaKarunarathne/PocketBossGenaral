import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session, send_from_directory, make_response
from datetime import datetime
import json
import uuid
from functools import wraps
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Production configuration
app.secret_key = os.environ.get('SECRET_KEY', 'fallback_secret_key_change_this')
app.config['SESSION_TYPE'] = 'filesystem'
app.permanent_session_lifetime = 28800
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = False

port = int(os.environ.get('PORT', 5000))

DATA_FOLDER = 'data'

# Ensure base folders exist
def ensure_base_folders():
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER)

def get_shop_folder(shop_name):
    """Get the data folder path for a specific shop"""
    return os.path.join(DATA_FOLDER, shop_name)

def get_shop_file_paths(shop_name):
    """Get file paths for a specific shop"""
    shop_folder = get_shop_folder(shop_name)
    return {
        'inventory': os.path.join(shop_folder, 'inventory.json'),
        'sales_folder': os.path.join(shop_folder, 'sales'),
        'expenses_folder': os.path.join(shop_folder, 'expenses')
    }

def ensure_shop_folders(shop_name):
    """Ensure all necessary folders exist for a shop"""
    shop_folder = get_shop_folder(shop_name)
    paths = get_shop_file_paths(shop_name)
    
    if not os.path.exists(shop_folder):
        os.makedirs(shop_folder)
    if not os.path.exists(paths['sales_folder']):
        os.makedirs(paths['sales_folder'])
    if not os.path.exists(paths['expenses_folder']):
        os.makedirs(paths['expenses_folder'])
    
    # Ensure credit.json exists
    credit_file = os.path.join(shop_folder, 'credit.json')
    if not os.path.exists(credit_file):
        default_credit_data = {'credits': []}
        with open(credit_file, 'w') as f:
            json.dump(default_credit_data, f, indent=4)

def load_shop_credentials():
    """Load shop credentials from environment variables"""
    shops = {}
    
    # Get all environment variables that start with SHOP_ and end with _PASSWORD
    for key, value in os.environ.items():
        if key.startswith('SHOP_') and key.endswith('_PASSWORD'):
            # Extract shop name from environment variable
            # SHOP_LUXURY_MOBILE_PASSWORD -> LUXURY_MOBILE -> Luxury Mobile
            shop_name_env = key[5:-9]  # Remove 'SHOP_' prefix and '_PASSWORD' suffix
            shop_name = shop_name_env.replace('_', ' ').title()
            shops[shop_name] = value
    
    return shops

def get_env_key_for_shop(shop_name):
    """Convert shop name to environment variable key format"""
    # Convert "Luxury Mobile" to "LUXURY_MOBILE"
    return shop_name.upper().replace(' ', '_')

def create_shop_credentials(shop_name, password):
    """Create credentials for a new shop by updating .env file"""
    ensure_base_folders()
    
    # Create shop data folders
    ensure_shop_folders(shop_name)
    
    # Get the environment variable key
    env_key = f"SHOP_{get_env_key_for_shop(shop_name)}_PASSWORD"
    
    # Read current .env file
    env_file_path = '.env'
    env_lines = []
    
    if os.path.exists(env_file_path):
        with open(env_file_path, 'r') as f:
            env_lines = f.readlines()
    
    # Check if the shop already exists in .env
    shop_exists = False
    for i, line in enumerate(env_lines):
        if line.startswith(f"{env_key}="):
            env_lines[i] = f"{env_key}={password}\n"
            shop_exists = True
            break
    
    # If shop doesn't exist, add it
    if not shop_exists:
        env_lines.append(f"{env_key}={password}\n")
    
    # Write back to .env file
    with open(env_file_path, 'w') as f:
        f.writelines(env_lines)
    
    # Reload environment variables
    load_dotenv(override=True)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in'] or 'shop_name' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def initialize_inventory():
    return {
        'inventory': []
    }

def initialize_daily_file(file_type):
    return {
        file_type: [],
        'daily_summary': {
            'sales_count': 0,
            'sales_amount': 0,
            'profit': 0,
            'expenses': 0
        } if file_type == 'sales' else {}
    }

def load_inventory():
    shop_name = session.get('shop_name')
    if not shop_name:
        return initialize_inventory()
    
    paths = get_shop_file_paths(shop_name)
    inventory_file = paths['inventory']
    
    if os.path.exists(inventory_file):
        with open(inventory_file, 'r') as f:
            return json.load(f)
    else:
        data = initialize_inventory()
        save_inventory(data)
        return data

def save_inventory(data):
    shop_name = session.get('shop_name')
    if not shop_name:
        return
    
    ensure_shop_folders(shop_name)
    paths = get_shop_file_paths(shop_name)
    
    with open(paths['inventory'], 'w') as f:
        json.dump(data, f, indent=4)

def get_daily_file_path(file_type):
    shop_name = session.get('shop_name')
    if not shop_name:
        return None
    
    today = datetime.now().strftime('%Y-%m-%d')
    paths = get_shop_file_paths(shop_name)
    folder = paths['sales_folder'] if file_type == 'sales' else paths['expenses_folder']
    return os.path.join(folder, f"{today}_{file_type}.json")

def load_daily_data(file_type):
    file_path = get_daily_file_path(file_type)
    if not file_path:
        return initialize_daily_file(file_type)
    
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        data = initialize_daily_file(file_type)
        save_daily_data(file_type, data)
        return data

def save_daily_data(file_type, data):
    file_path = get_daily_file_path(file_type)
    if not file_path:
        return
    
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def update_daily_summary(sales_data):
    sales = sales_data['sales']
    sales_amount = sum(sale['total_price'] for sale in sales)
    profit = sum(sale['profit'] for sale in sales)
    
    sales_data['daily_summary']['sales_count'] = len(sales)
    sales_data['daily_summary']['sales_amount'] = sales_amount
    sales_data['daily_summary']['profit'] = profit
    
    return sales_data

def get_all_daily_summaries():
    shop_name = session.get('shop_name')
    if not shop_name:
        return []
    
    summaries = []
    paths = get_shop_file_paths(shop_name)
    
    if not os.path.exists(paths['sales_folder']):
        return summaries
    
    for filename in os.listdir(paths['sales_folder']):
        if filename.endswith('_sales.json'):
            date = filename.split('_')[0]
            file_path = os.path.join(paths['sales_folder'], filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                summary = data.get('daily_summary', {})
                summary['date'] = date
                summaries.append(summary)
    
    for summary in summaries:
        date = summary['date']
        expense_file = os.path.join(paths['expenses_folder'], f"{date}_expenses.json")
        if os.path.exists(expense_file):
            with open(expense_file, 'r') as f:
                data = json.load(f)
                expenses_amount = sum(expense['amount'] for expense in data.get('expenses', []))
                summary['expenses'] = expenses_amount
        else:
            summary['expenses'] = 0
    
    return sorted(summaries, key=lambda x: x['date'], reverse=True)

def get_recent_sales(limit=5):
    shop_name = session.get('shop_name')
    if not shop_name:
        return []
    
    all_sales = []
    paths = get_shop_file_paths(shop_name)
    
    if not os.path.exists(paths['sales_folder']):
        return all_sales
    
    for filename in os.listdir(paths['sales_folder']):
        if filename.endswith('_sales.json'):
            file_path = os.path.join(paths['sales_folder'], filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                all_sales.extend(data.get('sales', []))
    
    return sorted(all_sales, key=lambda x: x['date'], reverse=True)[:limit]

def get_recent_expenses(limit=5):
    shop_name = session.get('shop_name')
    if not shop_name:
        return []
    
    all_expenses = []
    paths = get_shop_file_paths(shop_name)
    
    if not os.path.exists(paths['expenses_folder']):
        return all_expenses
    
    for filename in os.listdir(paths['expenses_folder']):
        if filename.endswith('_expenses.json'):
            file_path = os.path.join(paths['expenses_folder'], filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                all_expenses.extend(data.get('expenses', []))
    
    return sorted(all_expenses, key=lambda x: x['date'], reverse=True)[:limit]

def add_expense_record(category, description, amount):
    expenses_data = load_daily_data('expenses')
    
    new_expense = {
        'id': str(uuid.uuid4()),
        'category': category,
        'description': description,
        'amount': float(amount),
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    expenses_data['expenses'].append(new_expense)
    save_daily_data('expenses', expenses_data)
    
    return new_expense

def find_sale_by_id(sale_id):
    shop_name = session.get('shop_name')
    if not shop_name:
        return None, None, None
    
    paths = get_shop_file_paths(shop_name)
    
    if not os.path.exists(paths['sales_folder']):
        return None, None, None
    
    for filename in os.listdir(paths['sales_folder']):
        if filename.endswith('_sales.json'):
            file_path = os.path.join(paths['sales_folder'], filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                for sale in data.get('sales', []):
                    if sale['id'] == sale_id:
                        return sale, file_path, data
    return None, None, None

def return_items_to_inventory(sale):
    inventory_data = load_inventory()
    
    if sale.get('type') != 'trade_in':
        item = next((item for item in inventory_data['inventory'] if item['id'] == sale['item_id']), None)
        
        if item:
            item['quantity'] += sale['quantity']
        else:
            new_item = {
                'id': sale['item_id'],
                'name': sale['item_name'],
                'category': sale['category'],
                'model_number': sale['model_number'],
                'imei_number': sale.get('imei_number', ''),
                'purchase_price': (sale['total_price'] - sale['profit']) / sale['quantity'],
                'quantity': sale['quantity'],
                'supplier': 'Returned from sale',
                'date_added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            inventory_data['inventory'].append(new_item)
    
    elif sale.get('type') == 'trade_in':
        inventory_data['inventory'] = [item for item in inventory_data['inventory']
                                      if item['id'] != sale['item_id']]
    
    save_inventory(inventory_data)

def get_capital_file_path():
    """Get the capital file path for the current shop"""
    shop_name = session.get('shop_name')
    if not shop_name:
        return None
    shop_folder = get_shop_folder(shop_name)
    return os.path.join(shop_folder, 'capital.json')

def load_capital_data():
    """Load capital data for the current shop"""
    capital_file = get_capital_file_path()
    if not capital_file:
        return {'initial_capital': 0, 'current_capital': 0, 'daily_updates': []}
    
    if os.path.exists(capital_file):
        with open(capital_file, 'r') as f:
            return json.load(f)
    else:
        # Initialize with default values
        default_data = {
            'initial_capital': 0,
            'current_capital': 0,
            'daily_updates': []
        }
        save_capital_data(default_data)
        return default_data

def save_capital_data(data):
    """Save capital data for the current shop"""
    capital_file = get_capital_file_path()
    if not capital_file:
        return
    
    ensure_shop_folders(session['shop_name'])
    with open(capital_file, 'w') as f:
        json.dump(data, f, indent=4)

def update_daily_capital():
    """Update capital based on today's sales and expenses"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Get today's summary
    sales_data = load_daily_data('sales')
    expenses_data = load_daily_data('expenses')
    
    today_sales = sales_data.get('daily_summary', {}).get('sales_amount', 0)
    today_expenses = sum(expense['amount'] for expense in expenses_data.get('expenses', []))
    daily_profit = today_sales - today_expenses
    
    # Load capital data
    capital_data = load_capital_data()
    
    # Check if today's update already exists
    existing_update = next((update for update in capital_data['daily_updates'] 
                           if update['date'] == today), None)
    
    if existing_update:
        # Update existing entry
        old_profit = existing_update['daily_profit']
        existing_update.update({
            'sales': today_sales,
            'expenses': today_expenses,
            'daily_profit': daily_profit
        })
        # Adjust current capital
        capital_data['current_capital'] = capital_data['current_capital'] - old_profit + daily_profit
    else:
        # Add new daily update
        daily_update = {
            'date': today,
            'sales': today_sales,
            'expenses': today_expenses,
            'daily_profit': daily_profit,
            'capital_before': capital_data['current_capital'],
            'capital_after': capital_data['current_capital'] + daily_profit
        }
        capital_data['daily_updates'].append(daily_update)
        capital_data['current_capital'] += daily_profit
    
    # Sort daily updates by date (newest first)
    capital_data['daily_updates'].sort(key=lambda x: x['date'], reverse=True)
    
    save_capital_data(capital_data)
    return capital_data

def get_monthly_statistics():
    """Get monthly sales, expenses, and profit statistics"""
    shop_name = session.get('shop_name')
    if not shop_name:
        return []
    
    monthly_data = {}
    paths = get_shop_file_paths(shop_name)
    
    # Process sales data
    if os.path.exists(paths['sales_folder']):
        for filename in os.listdir(paths['sales_folder']):
            if filename.endswith('_sales.json'):
                date = filename.split('_')[0]
                month = date[:7]  # YYYY-MM format
                
                file_path = os.path.join(paths['sales_folder'], filename)
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    summary = data.get('daily_summary', {})
                    
                    if month not in monthly_data:
                        monthly_data[month] = {
                            'month': month,
                            'sales': 0,
                            'expenses': 0,
                            'profit': 0
                        }
                    
                    monthly_data[month]['sales'] += summary.get('sales_amount', 0)
                    monthly_data[month]['profit'] += summary.get('profit', 0)
    
    # Process expenses data
    if os.path.exists(paths['expenses_folder']):
        for filename in os.listdir(paths['expenses_folder']):
            if filename.endswith('_expenses.json'):
                date = filename.split('_')[0]
                month = date[:7]  # YYYY-MM format
                
                file_path = os.path.join(paths['expenses_folder'], filename)
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    expenses_amount = sum(expense['amount'] for expense in data.get('expenses', []))
                    
                    if month not in monthly_data:
                        monthly_data[month] = {
                            'month': month,
                            'sales': 0,
                            'expenses': 0,
                            'profit': 0
                        }
                    
                    monthly_data[month]['expenses'] += expenses_amount
    
    # Calculate final profit (sales profit - expenses)
    for month_data in monthly_data.values():
        month_data['profit'] = month_data['profit'] - month_data['expenses']
    
    # Return sorted by month (newest first)
    return sorted(monthly_data.values(), key=lambda x: x['month'], reverse=True)

# Add these new functions after the existing helper functions

def get_credit_file_path():
    """Get the credit file path for the current shop"""
    shop_name = session.get('shop_name')
    if not shop_name:
        return None
    shop_folder = get_shop_folder(shop_name)
    return os.path.join(shop_folder, 'credit.json')

def load_credit_data():
    """Load credit data for the current shop"""
    credit_file = get_credit_file_path()
    if not credit_file:
        return {'credits': []}
    
    if os.path.exists(credit_file):
        with open(credit_file, 'r') as f:
            return json.load(f)
    else:
        # Initialize with default structure
        default_data = {'credits': []}
        save_credit_data(default_data)
        return default_data

def save_credit_data(data):
    """Save credit data for the current shop"""
    credit_file = get_credit_file_path()
    if not credit_file:
        return
    
    ensure_shop_folders(session['shop_name'])
    with open(credit_file, 'w') as f:
        json.dump(data, f, indent=4)

def add_credit_record(customer_name, customer_phone, total_amount, credit_amount, due_date, description, sale_items):
    """Add a new credit record"""
    credit_data = load_credit_data()
    
    new_credit = {
        'id': str(uuid.uuid4()),
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'customer_name': customer_name,
        'customer_phone': customer_phone,
        'total_amount': float(total_amount),
        'credit_amount': float(credit_amount),
        'cash_amount': float(total_amount) - float(credit_amount),
        'due_date': due_date,
        'description': description,
        'status': 'pending',  # pending, paid, overdue
        'sale_items': sale_items,
        'payment_history': []
    }
    
    credit_data['credits'].append(new_credit)
    save_credit_data(credit_data)
    
    return new_credit

def get_all_credits():
    """Get all credit records for the current shop"""
    credit_data = load_credit_data()
    return credit_data.get('credits', [])

def find_credit_by_id(credit_id):
    """Find a credit record by ID"""
    credit_data = load_credit_data()
    for credit in credit_data.get('credits', []):
        if credit['id'] == credit_id:
            return credit, credit_data
    return None, None

def update_credit_status():
    """Update credit status based on due dates"""
    credit_data = load_credit_data()
    today = datetime.now().date()
    
    for credit in credit_data.get('credits', []):
        if credit['status'] == 'pending':
            due_date = datetime.strptime(credit['due_date'], '%Y-%m-%d').date()
            if today > due_date:
                credit['status'] = 'overdue'
    
    save_credit_data(credit_data)
    return credit_data

@app.route('/')
@login_required
def index():
    ensure_shop_folders(session['shop_name'])
    
    today_sales_data = load_daily_data('sales')
    today_summary = today_sales_data['daily_summary']
    today_summary['date'] = datetime.now().strftime('%Y-%m-%d')
    
    today_expenses_data = load_daily_data('expenses')
    expenses_amount = sum(expense['amount'] for expense in today_expenses_data.get('expenses', []))
    today_summary['expenses'] = expenses_amount
    
    recent_sales = get_recent_sales()
    recent_expenses = get_recent_expenses()
    
    inventory_data = load_inventory()
    low_stock = [item for item in inventory_data['inventory'] if item['quantity'] < 5]
    
    return render_template('index.html',
                           summary=today_summary,
                           recent_sales=recent_sales,
                           recent_expenses=recent_expenses,
                           low_stock=low_stock,
                           shop_name=session['shop_name'])

@app.context_processor
def override_url_for():
    return dict(url_for=dated_url_for)

def dated_url_for(endpoint, **values):
    if endpoint == 'static':
        filename = values.get('filename', None)
        if filename:
            file_path = os.path.join(app.root_path, 'static', filename)
            if os.path.exists(file_path):
                values['v'] = int(os.stat(file_path).st_mtime)
            else:
                values['v'] = int(time.time())
    return url_for(endpoint, **values)

@app.route('/static/<path:filename>')
def static_files(filename):
    response = send_from_directory(app.static_folder, filename)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.after_request
def after_request(response):
    if request.endpoint == 'static' or (request.path and request.path.startswith('/static/')):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    return response

@app.route('/inventory')
@login_required
def inventory():
    ensure_shop_folders(session['shop_name'])
    inventory_data = load_inventory()
    return render_template('inventory.html', inventory=inventory_data['inventory'], shop_name=session['shop_name'])

@app.route('/add_multiple_inventory', methods=['POST'])
@login_required
def add_multiple_inventory():
    ensure_shop_folders(session['shop_name'])
    inventory_data = load_inventory()
    
    form_data = request.form
    
    item_index = 0
    while True:
        item_name_key = f'items[{item_index}][name]'
        if item_name_key not in form_data:
            break
        
        category = form_data[f'items[{item_index}][category]']
        quantity = int(form_data[f'items[{item_index}][quantity]'])
        purchase_price = float(form_data[f'items[{item_index}][purchase_price]'])
        
        new_item = {
            'id': str(uuid.uuid4()),
            'name': form_data[f'items[{item_index}][name]'],
            'category': category,
            'model_number': form_data[f'items[{item_index}][model_number]'],
            'imei_number': '',
            'purchase_price': purchase_price,
            'quantity': quantity,
            'supplier': form_data.get(f'items[{item_index}][supplier]', ''),
            'date_added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        inventory_data['inventory'].append(new_item)
        
        add_expense_record(
            'Inventory Purchase',
            f"{category}: {new_item['name']} (Model: {new_item['model_number']}, Qty: {quantity})",
            purchase_price * quantity
        )
        
        item_index += 1
    
    save_inventory(inventory_data)
    return redirect(url_for('inventory'))

@app.route('/edit_inventory_item/<item_id>', methods=['GET', 'POST'])
@login_required
def edit_inventory_item(item_id):
    inventory_data = load_inventory()
    
    item_index = next((i for i, item in enumerate(inventory_data['inventory'])
                      if item['id'] == item_id), None)
    
    if item_index is None:
        flash('Item not found', 'error')
        return redirect(url_for('inventory'))
    
    if request.method == 'POST':
        item = inventory_data['inventory'][item_index]
        
        item['name'] = request.form['name']
        item['category'] = request.form['category']
        item['model_number'] = request.form['model_number']
        item['imei_number'] = ''
        item['purchase_price'] = float(request.form['purchase_price'])
        item['quantity'] = int(request.form['quantity'])
        item['supplier'] = request.form['supplier']
        
        save_inventory(inventory_data)
        flash('Item updated successfully', 'success')
        return redirect(url_for('inventory'))
    
    return render_template('edit_inventory.html', item=inventory_data['inventory'][item_index])

@app.route('/delete_inventory_item/<item_id>', methods=['POST'])
@login_required
def delete_inventory_item(item_id):
    inventory_data = load_inventory()
    
    inventory_data['inventory'] = [item for item in inventory_data['inventory']
                                  if item['id'] != item_id]
    
    save_inventory(inventory_data)
    flash('Item deleted successfully', 'success')
    return redirect(url_for('inventory'))

@app.route('/sales')
@login_required
def sales():
    ensure_shop_folders(session['shop_name'])
    sales_data = load_daily_data('sales')
    inventory_data = load_inventory()
    
    return render_template('sales.html',
                           sales=sales_data['sales'],
                           inventory=inventory_data['inventory'],
                           shop_name=session['shop_name'])

@app.route('/sales2')
@login_required
def sales2_view():
    ensure_shop_folders(session['shop_name'])
    sales_data = load_daily_data('sales')
    inventory_data = load_inventory()
    
    return render_template('sales2.html',
                           sales=sales_data['sales'],
                           inventory=inventory_data['inventory'],
                           shop_name=session['shop_name'])

def cleanup_zero_quantity_items():
    """Remove items with 0 quantity from inventory"""
    inventory_data = load_inventory()
    original_count = len(inventory_data['inventory'])
    
    # Filter out items with 0 quantity
    inventory_data['inventory'] = [item for item in inventory_data['inventory'] if item['quantity'] > 0]
    
    # Save if any items were removed
    if len(inventory_data['inventory']) < original_count:
        save_inventory(inventory_data)
        removed_count = original_count - len(inventory_data['inventory'])
        print(f"Removed {removed_count} items with 0 quantity")

@app.route('/add_multiple_sales', methods=['POST'])
@login_required
def add_multiple_sales():
    ensure_shop_folders(session['shop_name'])
    inventory_data = load_inventory()
    sales_data = load_daily_data('sales')

    cleanup_zero_quantity_items()
    
    customer_name = request.form['customer_name']
    customer_phone = request.form['customer_phone']
    
    # Parse payment data from frontend
    payment_data = json.loads(request.form.get('payment_data', '{}'))
    payment_method = payment_data.get('payment_method', request.form.get('payment_method', 'Cash'))
    payment_details = payment_data.get('payment_details', request.form.get('payment_details', ''))
    
    # Calculate cash and credit amounts based on payment method
    total_cart_amount = 0
    cart_data = json.loads(request.form['cart_data'])
    trade_in_data = json.loads(request.form.get('trade_in_data', '[]'))
    borrowed_items_data = json.loads(request.form.get('borrowed_items_data', '[]'))
    
    # Calculate total amount first
    for cart_item in cart_data:
        total_cart_amount += cart_item['quantity'] * cart_item['sellingPrice']
    
    for borrowed_item in borrowed_items_data:
        total_cart_amount += int(borrowed_item['quantity']) * float(borrowed_item['selling_price'])
    
    # Subtract trade-in values
    for trade_in in trade_in_data:
        total_cart_amount -= float(trade_in['trade_in_value'])
    
    # Determine cash and credit amounts based on payment method
    if payment_method == 'Partial Payment':
        amount_paid = float(request.form.get('amount_paid', 0))
        cash_amount = amount_paid
        credit_amount = total_cart_amount - amount_paid
        due_date = request.form.get('due_date', '')
        credit_description = f"Partial payment - Remaining amount for {customer_name}"
        check_number = ''
    elif payment_method == 'Cheque':
        cash_amount = 0
        credit_amount = total_cart_amount
        due_date = request.form.get('due_date', '')
        credit_description = f"Cheque payment - {payment_details}"
        check_number = payment_details  # Assuming payment_details contains check number for cheque
    elif payment_method in ['Cash', 'Card', 'UPI', 'Bank Transfer']:
        cash_amount = total_cart_amount
        credit_amount = 0
        due_date = ''
        credit_description = ''
        check_number = ''
    else:
        # Default to cash
        cash_amount = total_cart_amount
        credit_amount = 0
        due_date = ''
        credit_description = ''
        check_number = ''
    
    sale_items = []
    total_amount = 0
    
    # Process regular sales
    for cart_item in cart_data:
        item_id = cart_item['id']
        quantity = cart_item['quantity']
        selling_price = cart_item['sellingPrice']
        imei_number = cart_item.get('imei_number', '')
        
        item = next((item for item in inventory_data['inventory'] if item['id'] == item_id), None)
        
        if item and item['quantity'] >= quantity:
            item['quantity'] -= quantity
            
            total_price = selling_price * quantity
            profit = (selling_price - item['purchase_price']) * quantity
            
            # Calculate proportional cash and credit amounts for this item
            item_cash_amount = (cash_amount / total_cart_amount * total_price) if total_cart_amount > 0 else total_price
            item_credit_amount = (credit_amount / total_cart_amount * total_price) if total_cart_amount > 0 else 0
            
            new_sale = {
                'id': str(uuid.uuid4()),
                'customer_name': customer_name,
                'customer_phone': customer_phone,
                'item_id': item_id,
                'item_name': item['name'],
                'category': item['category'],
                'model_number': item['model_number'],
                'imei_number': imei_number,
                'quantity': quantity,
                'unit_price': selling_price,
                'total_price': total_price,
                'profit': profit,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'type': 'regular',
                'payment_method': payment_method,
                'payment_details': payment_details,
                'credit_amount': round(item_credit_amount, 2),
                'cash_amount': round(item_cash_amount, 2)
            }
            
            sales_data['sales'].append(new_sale)
            sale_items.append(new_sale)
            total_amount += total_price
    
    # Process trade-ins
    for trade_in in trade_in_data:
        new_inventory_item = {
            'id': str(uuid.uuid4()),
            'name': trade_in['name'],
            'category': 'Phone',
            'model_number': trade_in['model_number'],
            'imei_number': trade_in.get('imei_number', ''),
            'purchase_price': float(trade_in['trade_in_value']),
            'quantity': 1,
            'supplier': 'Trade-in',
            'date_added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        inventory_data['inventory'].append(new_inventory_item)
        
        trade_in_sale = {
            'id': str(uuid.uuid4()),
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'item_id': new_inventory_item['id'],
            'item_name': trade_in['name'],
            'category': 'Phone',
            'model_number': trade_in['model_number'],
            'imei_number': trade_in['imei_number'],
            'quantity': 1,
            'unit_price': -float(trade_in['trade_in_value']),
            'total_price': -float(trade_in['trade_in_value']),
            'profit': 0,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'trade_in',
            'payment_method': payment_method,
            'payment_details': payment_details,
            'credit_amount': 0,  # Trade-ins don't affect credit calculation
            'cash_amount': -float(trade_in['trade_in_value'])
        }
        
        sales_data['sales'].append(trade_in_sale)
        sale_items.append(trade_in_sale)
        total_amount -= float(trade_in['trade_in_value'])
        
        add_expense_record(
            'Trade-in Purchase',
            f"Trade-in Phone: {trade_in['name']} (Model: {trade_in['model_number']}, IMEI: {trade_in['imei_number']})",
            float(trade_in['trade_in_value'])
        )
    
    # Process borrowed items
    for borrowed_item in borrowed_items_data:
        new_inventory_item = {
            'id': str(uuid.uuid4()),
            'name': borrowed_item['name'],
            'category': borrowed_item['category'],
            'model_number': borrowed_item['model_number'],
            'imei_number': borrowed_item.get('imei_number', ''),
            'purchase_price': float(borrowed_item['purchase_price']),
            'quantity': int(borrowed_item['quantity']),
            'supplier': 'Borrowed',
            'date_added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        inventory_data['inventory'].append(new_inventory_item)
        
        add_expense_record(
            'Borrowed Item Purchase',
            f"Borrowed {borrowed_item['category']}: {borrowed_item['name']} (Model: {borrowed_item['model_number']})",
            float(borrowed_item['purchase_price']) * int(borrowed_item['quantity'])
        )
        
        selling_price = float(borrowed_item['selling_price'])
        quantity = int(borrowed_item['quantity'])
        total_price = selling_price * quantity
        profit = (selling_price - float(borrowed_item['purchase_price'])) * quantity
        
        # Calculate proportional cash and credit amounts for this item
        item_cash_amount = (cash_amount / total_cart_amount * total_price) if total_cart_amount > 0 else total_price
        item_credit_amount = (credit_amount / total_cart_amount * total_price) if total_cart_amount > 0 else 0
        
        new_inventory_item['quantity'] = 0
        
        borrowed_sale = {
            'id': str(uuid.uuid4()),
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'item_id': new_inventory_item['id'],
            'item_name': borrowed_item['name'],
            'category': borrowed_item['category'],
            'model_number': borrowed_item['model_number'],
            'imei_number': borrowed_item.get('imei_number', ''),
            'quantity': quantity,
            'unit_price': selling_price,
            'total_price': total_price,
            'profit': profit,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'borrowed_and_sold',
            'payment_method': payment_method,
            'payment_details': payment_details,
            'credit_amount': round(item_credit_amount, 2),
            'cash_amount': round(item_cash_amount, 2)
        }
        
        sales_data['sales'].append(borrowed_sale)
        sale_items.append(borrowed_sale)
        total_amount += total_price
    
    # Handle credit transactions - Save to credit.json
    if credit_amount > 0:
        if payment_method in ['Partial Payment', 'Cheque'] and not due_date:
            return "Error: Due date is required for credit transactions", 400
        
        # Save credit transaction to credit.json
        save_credit_transaction(
            customer_name=customer_name,
            customer_phone=customer_phone,
            credit_amount=credit_amount,
            due_date=due_date,
            check_number=check_number,
            description=credit_description,
            payment_method=payment_method
        )
        
        # Add credit record (keeping your existing function)
        add_credit_record(
            customer_name=customer_name,
            customer_phone=customer_phone,
            total_amount=total_amount,
            credit_amount=credit_amount,
            due_date=due_date,
            description=credit_description,
            sale_items=sale_items
        )
    
    sales_data = update_daily_summary(sales_data)
    save_inventory(inventory_data)
    save_daily_data('sales', sales_data)
    
    receipt_data = {
        'receipt_id': f"REC-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'customer_name': customer_name,
        'customer_phone': customer_phone,
        'sale_items': sale_items,
        'total': total_amount,
        'payment_method': payment_method,
        'payment_details': payment_details,
        'cash_amount': cash_amount,
        'credit_amount': credit_amount,
        'due_date': due_date if credit_amount > 0 else None
    }
    
    # Get shop name from session
    shop_name = session.get('shop_name')
    
    if not shop_name:
        return "Error: Shop name not found in session", 400
    
    # Load shop-specific receipt template
    try:
        shop_receipt_path = f"data/{shop_name}/receipt.html"
        
        # Check if shop-specific receipt template exists
        if not os.path.exists(shop_receipt_path):
            return f"Error: Receipt template not found for shop '{shop_name}' at {shop_receipt_path}", 404
        
        # Read the shop-specific receipt template
        with open(shop_receipt_path, 'r', encoding='utf-8') as file:
            receipt_template_content = file.read()
        
        # Create a Jinja2 template from the file content with Flask's environment
        from jinja2 import Template
        template = app.jinja_env.from_string(receipt_template_content)
        
        # Render the template with receipt data and Flask context
        with app.app_context():
            rendered_receipt = template.render(receipt=receipt_data)
        
        # Update capital after sales
        update_daily_capital()
        
        return rendered_receipt
        
    except FileNotFoundError:
        return f"Error: Receipt template file not found for shop '{shop_name}'", 404
    except Exception as e:
        return f"Error loading receipt template: {str(e)}", 500


def save_credit_transaction(customer_name, customer_phone, credit_amount, due_date, check_number, description, payment_method):
    """Save credit transaction to credit.json file"""
    shop_name = session.get('shop_name')
    if not shop_name:
        return
    
    credit_file_path = f"data/{shop_name}/credit.json"
    
    # Load existing credit data or create new structure
    try:
        if os.path.exists(credit_file_path):
            with open(credit_file_path, 'r', encoding='utf-8') as file:
                credit_data = json.load(file)
        else:
            credit_data = {'credits': []}
    except (json.JSONDecodeError, FileNotFoundError):
        credit_data = {'credits': []}
    
    # Create new credit record
    new_credit = {
        'id': str(uuid.uuid4()),
        'customer_name': customer_name,
        'customer_phone': customer_phone,
        'credit_amount': round(credit_amount, 2),
        'due_date': due_date,
        'check_number': check_number,
        'description': description,
        'payment_method': payment_method,
        'date_created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'pending'  # You can add status tracking
    }
    
    # Add to credits list
    credit_data['credits'].append(new_credit)
    
    # Save back to file
    try:
        with open(credit_file_path, 'w', encoding='utf-8') as file:
            json.dump(credit_data, file, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving credit transaction: {str(e)}")


def load_credit_data():
    """Load credit data from credit.json file"""
    shop_name = session.get('shop_name')
    if not shop_name:
        return {'credits': []}
    
    credit_file_path = f"data/{shop_name}/credit.json"
    
    try:
        if os.path.exists(credit_file_path):
            with open(credit_file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        else:
            return {'credits': []}
    except (json.JSONDecodeError, FileNotFoundError):
        return {'credits': []}


def update_credit_status(credit_id, status, payment_amount=0):
    """Update credit transaction status (e.g., paid, partially_paid)"""
    shop_name = session.get('shop_name')
    if not shop_name:
        return False
    
    credit_file_path = f"data/{shop_name}/credit.json"
    credit_data = load_credit_data()
    
    # Find and update the credit record
    for credit in credit_data['credits']:
        if credit['id'] == credit_id:
            credit['status'] = status
            if payment_amount > 0:
                credit['paid_amount'] = credit.get('paid_amount', 0) + payment_amount
                credit['remaining_amount'] = credit['credit_amount'] - credit.get('paid_amount', 0)
                credit['last_payment_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            break
    
    # Save updated data
    try:
        with open(credit_file_path, 'w', encoding='utf-8') as file:
            json.dump(credit_data, file, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error updating credit status: {str(e)}")
        return False

@app.route('/delete_sale/<sale_id>', methods=['POST'])
@login_required
def delete_sale(sale_id):
    sale, file_path, sales_data = find_sale_by_id(sale_id)
    
    if not sale:
        flash('Sale not found', 'error')
        return redirect(url_for('sales'))
    
    return_items_to_inventory(sale)
    
    sales_data['sales'] = [s for s in sales_data['sales'] if s['id'] != sale_id]
    
    sales_data = update_daily_summary(sales_data)
    
    with open(file_path, 'w') as f:
        json.dump(sales_data, f, indent=4)
    
    flash('Sale deleted and items returned to inventory', 'success')
    return redirect(url_for('sales'))

@app.route('/expenses')
@login_required
def expenses():
    ensure_shop_folders(session['shop_name'])
    expenses_data = load_daily_data('expenses')
    return render_template('expenses.html', expenses=expenses_data['expenses'], shop_name=session['shop_name'])

@app.route('/add_expense', methods=['POST'])
@login_required
def add_expense():
    ensure_shop_folders(session['shop_name'])
    
    category = request.form['category']
    description = request.form['description']
    amount = float(request.form['amount'])
    
    add_expense_record(category, description, amount)
    # Update capital after expense
    update_daily_capital()

    return redirect(url_for('expenses'))

@app.route('/reports')
@login_required
def reports():
    ensure_shop_folders(session['shop_name'])
    
    selected_date = request.args.get('date')
    selected_month = request.args.get('month')
    
    daily_summaries = get_all_daily_summaries()
    
    total_sales = sum(summary.get('sales_amount', 0) for summary in daily_summaries)
    total_profit = sum(summary.get('profit', 0) for summary in daily_summaries)
    total_expenses = sum(summary.get('expenses', 0) for summary in daily_summaries)
    
    today = datetime.now().strftime('%Y-%m-%d')
    today_sales = 0
    today_profit = 0
    today_expenses = 0
    
    for summary in daily_summaries:
        if summary.get('date') == today:
            today_sales = summary.get('sales_amount', 0)
            today_profit = summary.get('profit', 0)
            today_expenses = summary.get('expenses', 0)
            break
    
    selected_date_stats = None
    if selected_date:
        for summary in daily_summaries:
            if summary.get('date') == selected_date:
                selected_date_stats = {
                    'date': selected_date,
                    'sales': summary.get('sales_amount', 0),
                    'expenses': summary.get('expenses', 0),
                    'profit': summary.get('sales_amount', 0) - summary.get('expenses', 0)
                }
                break
        
        if not selected_date_stats:
            selected_date_stats = {
                'date': selected_date,
                'sales': 0,
                'expenses': 0,
                'profit': 0
            }
    
    monthly_stats = get_monthly_statistics()
    
    selected_month_stats = None
    if selected_month:
        selected_month_stats = next(
            (month for month in monthly_stats if month['month'] == selected_month),
            {'month': selected_month, 'sales': 0, 'expenses': 0, 'profit': 0}
        )
    
    # Initialize all_sales BEFORE the if block
    all_sales = []
    paths = get_shop_file_paths(session['shop_name'])
    
    if os.path.exists(paths['sales_folder']):
        for filename in os.listdir(paths['sales_folder']):
            if filename.endswith('_sales.json'):
                file_path = os.path.join(paths['sales_folder'], filename)
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    all_sales.extend(data.get('sales', []))
    
    item_sales = {}
    for sale in all_sales:
        if sale.get('type') == 'trade_in':
            continue
        
        item_name = sale['item_name']
        if item_name in item_sales:
            item_sales[item_name]['quantity'] += sale['quantity']
            item_sales[item_name]['revenue'] += sale['total_price']
            item_sales[item_name]['profit'] += sale['profit']
        else:
            item_sales[item_name] = {
                'quantity': sale['quantity'],
                'revenue': sale['total_price'],
                'profit': sale['profit']
            }
    
    top_items = sorted(
        [{'name': name, **stats} for name, stats in item_sales.items()],
        key=lambda x: x['revenue'],
        reverse=True
    )[:10]
    
    # Load capital data and update it
    capital_data = update_daily_capital()
    
    return render_template('reports.html',
                         daily_summaries=daily_summaries,
                         total_sales=total_sales,
                         total_profit=total_profit,
                         total_expenses=total_expenses,
                         top_items=top_items,
                         today_sales=today_sales,
                         today_profit=today_profit,
                         today_expenses=today_expenses,
                         selected_date_stats=selected_date_stats,
                         monthly_stats=monthly_stats,
                         selected_month_stats=selected_month_stats,
                         capital_data=capital_data,
                         shop_name=session['shop_name'])

@app.route('/get_inventory_item/<item_id>', methods=['GET'])
@login_required
def get_inventory_item(item_id):
    inventory_data = load_inventory()
    item = next((item for item in inventory_data['inventory'] if item['id'] == item_id), None)
    
    if item:
        return jsonify(item)
    else:
        return jsonify({'error': 'Item not found'}), 404

@app.route('/add_trade_in', methods=['POST'])
@login_required
def add_trade_in():
    data = request.get_json()
    
    required_fields = ['name', 'model_number', 'imei_number', 'trade_in_value']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    return jsonify({'success': True, 'trade_in': data})

@app.route('/add_borrowed_item', methods=['POST'])
@login_required
def add_borrowed_item():
    data = request.get_json()
    
    required_fields = ['name', 'category', 'model_number', 'purchase_price', 'selling_price', 'quantity']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    return jsonify({'success': True, 'borrowed_item': data})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        shop_name = request.form['shop_name'].strip()
        password = request.form['password']
        remember_username = request.form.get('remember_username')
        
        shop_credentials = load_shop_credentials()
        
        # Check if shop exists and password matches
        if shop_name in shop_credentials and password == shop_credentials[shop_name]:
            session['logged_in'] = True
            session['shop_name'] = shop_name
            session.permanent = True
            
            # Handle remember username functionality
            if remember_username:
                resp = make_response(redirect(url_for('sales')))  # Changed from 'index' to 'sales'
                resp.set_cookie('remembered_username', shop_name, max_age=30*24*60*60)  # 30 days
                flash(f'Login successful! Welcome to {shop_name}', 'success')
                return resp
            else:
                resp = make_response(redirect(url_for('sales')))  # Changed from 'index' to 'sales'
                resp.set_cookie('remembered_username', '', expires=0)
                flash(f'Login successful! Welcome to {shop_name}', 'success')
                return resp
        else:
            flash('Invalid shop name or password. Please try again.', 'error')
    
    # For GET request, check if there's a remembered username
    remembered_username = request.cookies.get('remembered_username', '')
    
    # Get available shops for dropdown (optional)
    available_shops = list(load_shop_credentials().keys())
    
    return render_template('login.html',
                          remembered_username=remembered_username,
                         available_shops=available_shops)


@app.route('/logout')
def logout():
    shop_name = session.get('shop_name', 'Unknown')
    session.pop('logged_in', None)
    session.pop('shop_name', None)
    flash(f'You have been logged out from {shop_name}.', 'info')
    return redirect(url_for('login'))

@app.route('/clear_remembered_username', methods=['POST'])
def clear_remembered_username():
    """Clear the remembered username"""
    from flask import make_response
    resp = make_response('{"success": true}', 200)
    resp.headers['Content-Type'] = 'application/json'
    resp.set_cookie('remembered_username', '', expires=0)
    return resp


@app.route('/register_shop', methods=['GET', 'POST'])
def register_shop():
    if request.method == 'POST':
        shop_name = request.form['shop_name'].strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Validation
        if not shop_name:
            flash('Shop name is required.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
        elif password != confirm_password:
            flash('Passwords do not match.', 'error')
        else:
            # Check if shop already exists
            shop_credentials = load_shop_credentials()
            if shop_name in shop_credentials:
                flash('Shop name already exists. Please choose a different name.', 'error')
            else:
                # Create new shop
                create_shop_credentials(shop_name, password)
                flash(f'Shop "{shop_name}" registered successfully! You can now login.', 'success')
                return redirect(url_for('login'))
    
    return render_template('register_shop.html')

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        shop_name = session['shop_name']
        shop_credentials = load_shop_credentials()
        
        if current_password != shop_credentials[shop_name]:
            flash('Current password is incorrect.', 'error')
        elif new_password != confirm_password:
            flash('New passwords do not match.', 'error')
        elif len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
        else:
            # Update password
            credentials_file = os.path.join(CREDENTIALS_FOLDER, f'{shop_name}.json')
            shop_data = {
                "shop_name": shop_name,
                "password": new_password
            }
            with open(credentials_file, 'w') as f:
                json.dump(shop_data, f, indent=4)
            
            flash('Password changed successfully!', 'success')
            return redirect(url_for('index'))
    
    return render_template('change_password.html', shop_name=session['shop_name'])

@app.route('/shop_info')
@login_required
def shop_info():
    """Display shop information and statistics"""
    shop_name = session['shop_name']
    
    # Get shop statistics
    daily_summaries = get_all_daily_summaries()
    inventory_data = load_inventory()
    
    total_sales = sum(summary.get('sales_amount', 0) for summary in daily_summaries)
    total_profit = sum(summary.get('profit', 0) for summary in daily_summaries)
    total_expenses = sum(summary.get('expenses', 0) for summary in daily_summaries)
    total_items = len(inventory_data['inventory'])
    total_stock = sum(item['quantity'] for item in inventory_data['inventory'])
    
    shop_stats = {
        'shop_name': shop_name,
        'total_sales': total_sales,
        'total_profit': total_profit,
        'total_expenses': total_expenses,
        'net_profit': total_profit - total_expenses,
        'total_items': total_items,
        'total_stock': total_stock,
        'days_active': len(daily_summaries)
    }
    
    return render_template('shop_info.html', shop_stats=shop_stats)

@app.route('/delete_expense/<expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    """Delete an expense record"""
    expenses_data = load_daily_data('expenses')
    
    # Find and remove the expense
    original_count = len(expenses_data['expenses'])
    expenses_data['expenses'] = [expense for expense in expenses_data['expenses'] 
                                if expense['id'] != expense_id]
    
    if len(expenses_data['expenses']) < original_count:
        save_daily_data('expenses', expenses_data)
        flash('Expense deleted successfully', 'success')
    else:
        flash('Expense not found', 'error')
    
    return redirect(url_for('expenses'))

@app.route('/get_receipt_data')
@login_required
def get_receipt_data():
    try:
        sale_id = request.args.get('sale_id')
        customer_name = request.args.get('customer')
        customer_phone = request.args.get('phone')
        sale_date = request.args.get('date')
        
        if not all([sale_id, customer_name, customer_phone, sale_date]):
            return jsonify({'error': 'Missing required parameters'}), 400
        
        # Load sales data
        sales_data = load_daily_data('sales')
        
        # Find all sales for this customer on this date
        customer_sales = []
        for sale in sales_data.get('sales', []):
            sale_date_only = sale['date'].split(' ')[0]  # Get date part only
            if (sale['customer_name'] == customer_name and 
                sale['customer_phone'] == customer_phone and 
                sale_date_only == sale_date):
                customer_sales.append(sale)
        
        if not customer_sales:
            return jsonify({'error': 'No sales found for this customer on this date'}), 404
        
        # Separate items by type
        regular_items = []
        trade_ins = []
        borrowed_items = []
        
        for sale in customer_sales:
            if sale.get('type') == 'trade_in':
                trade_ins.append({
                    'name': sale['item_name'],
                    'model_number': sale['model_number'],
                    'imei_number': sale.get('imei_number', ''),
                    'trade_in_value': abs(sale['unit_price'])  # Make positive for display
                })
            elif sale.get('type') == 'borrowed_and_sold':
                borrowed_items.append({
                    'name': sale['item_name'],
                    'model_number': sale['model_number'],
                    'category': sale['category'],
                    'quantity': sale['quantity'],
                    'selling_price': sale['unit_price']
                })
            else:  # regular sale
                regular_items.append({
                    'name': sale['item_name'],
                    'model_number': sale['model_number'],
                    'category': sale['category'],
                    'imei_number': sale.get('imei_number', ''),
                    'quantity': sale['quantity'],
                    'selling_price': sale['unit_price']
                })
        
        # Use the first sale for basic info
        first_sale = customer_sales[0]
        
        receipt_data = {
            'sale': {
                'id': f"REC-{first_sale['date'].replace(' ', '').replace(':', '').replace('-', '')}",
                'customer_name': customer_name,
                'customer_phone': customer_phone,
                'sale_date': first_sale['date']
            },
            'items': regular_items,
            'trade_ins': trade_ins,
            'borrowed_items': borrowed_items
        }
        
        return jsonify(receipt_data)
        
    except Exception as e:
        return jsonify({'error': f'Failed to load receipt data: {str(e)}'}), 500
    
@app.route('/set_initial_capital', methods=['POST'])
@login_required
def set_initial_capital():
    """Set or update the initial capital"""
    try:
        initial_capital = float(request.form['initial_capital'])
        
        capital_data = load_capital_data()
        old_initial = capital_data['initial_capital']
        difference = initial_capital - old_initial
        
        capital_data['initial_capital'] = initial_capital
        capital_data['current_capital'] += difference
        
        save_capital_data(capital_data)
        flash(f'Initial capital set to ${initial_capital:,.2f}', 'success')
        
    except ValueError:
        flash('Please enter a valid number for initial capital', 'error')
    
    return redirect(url_for('reports'))

@app.route('/update_capital', methods=['POST'])
@login_required
def update_capital():
    """Manually trigger capital update for today"""
    try:
        capital_data = update_daily_capital()
        flash('Capital updated successfully', 'success')
    except Exception as e:
        flash(f'Error updating capital: {str(e)}', 'error')
    
    return redirect(url_for('reports'))


@app.route('/get_credit_details/<credit_id>')
@login_required
def get_credit_details(credit_id):
    """Get detailed information about a specific credit"""
    credit_data = load_credit_data()
    
    for credit in credit_data['credits']:
        if credit['id'] == credit_id:
            return jsonify(credit)
    
    return jsonify({'error': 'Credit not found'}), 404


@app.route('/mark_credit_overdue/<credit_id>', methods=['POST'])
@login_required
def mark_credit_overdue(credit_id):
    """Mark a credit as overdue"""
    success = update_credit_status(credit_id, 'overdue')
    return jsonify({'success': success})


@app.route('/pay_credit', methods=['POST'])
@login_required
def pay_credit():
    """Handle credit payment with enhanced functionality"""
    credit_id = request.form['credit_id']
    payment_amount = float(request.form['payment_amount'])
    payment_method = request.form['payment_method']
    payment_notes = request.form.get('payment_notes', '')
    
    credit_data = load_credit_data()
    credit_record = None
    
    # Find the credit record
    for credit in credit_data['credits']:
        if credit['id'] == credit_id:
            credit_record = credit
            break
    
    if not credit_record:
        flash('Credit record not found', 'error')
        return redirect(url_for('view_credits'))
    
    remaining_amount = credit_record['credit_amount'] - credit_record.get('paid_amount', 0)
    
    if payment_amount > remaining_amount:
        flash('Payment amount cannot exceed remaining amount', 'error')
        return redirect(url_for('view_credits'))
    
    # Update credit record with payment details
    if 'payments' not in credit_record:
        credit_record['payments'] = []
    
    payment_record = {
        'id': str(uuid.uuid4()),
        'amount': payment_amount,
        'method': payment_method,
        'notes': payment_notes,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    credit_record['payments'].append(payment_record)
    
    if payment_amount >= remaining_amount:
        # Full payment
        update_credit_status(credit_id, 'paid', payment_amount)
        flash(f'Credit fully paid! Amount: ₹{payment_amount}', 'success')
    else:
        # Partial payment
        update_credit_status(credit_id, 'partially_paid', payment_amount)
        flash(f'Partial payment recorded! Amount: ₹{payment_amount}', 'success')
    
    return redirect(url_for('view_credits'))

from datetime import datetime, timedelta
import json
import os

# Add these routes to your existing Flask app

@app.route('/credits')
@login_required
def credits():
    """Display credit management page"""
    ensure_shop_folders(session['shop_name'])
    credits_data = load_credit_data()
    
    # Process credits for display
    processed_credits = []
    total_pending = 0
    overdue_count = 0
    month_collected = 0
    
    current_date = datetime.now().date()
    current_month = current_date.month
    current_year = current_date.year
    
    for credit in credits_data.get('credits', []):
        # Calculate due status
        due_date = datetime.strptime(credit['due_date'], '%Y-%m-%d').date()
        days_until_due = (due_date - current_date).days
        
        if credit['status'] == 'pending':
            if days_until_due < 0:
                credit['due_status'] = 'overdue'
                overdue_count += 1
            elif days_until_due <= 7:
                credit['due_status'] = 'due_soon'
            else:
                credit['due_status'] = 'normal'
            
            total_pending += credit['credit_amount']
        else:
            credit['due_status'] = 'paid'
            
        # Calculate monthly collections
        for payment in credit.get('payment_history', []):
            payment_date = datetime.strptime(payment['date'], '%Y-%m-%d %H:%M:%S')
            if payment_date.month == current_month and payment_date.year == current_year:
                month_collected += payment['amount']
        
        processed_credits.append(credit)
    
    return render_template('credit.html', 
                         credits=processed_credits,
                         total_pending=total_pending,
                         overdue_count=overdue_count,
                         month_collected=month_collected)

@app.route('/credit_details/<credit_id>')
@login_required
def credit_details(credit_id):
    """Get detailed view of a specific credit"""
    ensure_shop_folders(session['shop_name'])
    credits_data = load_credit_data()
    
    credit = next((c for c in credits_data.get('credits', []) if c['id'] == credit_id), None)
    
    if not credit:
        return "Credit not found", 404
    
    # Calculate remaining amount
    total_paid = sum(payment['amount'] for payment in credit.get('payment_history', []))
    remaining_amount = credit['credit_amount'] - total_paid
    
    html_content = f"""
    <div class="row">
        <div class="col-md-6">
            <h6>Customer Information</h6>
            <table class="table table-sm">
                <tr><td><strong>Name:</strong></td><td>{credit['customer_name']}</td></tr>
                <tr><td><strong>Phone:</strong></td><td>{credit['customer_phone']}</td></tr>
                <tr><td><strong>Date:</strong></td><td>{credit['date']}</td></tr>
                <tr><td><strong>Due Date:</strong></td><td>{credit['due_date']}</td></tr>
            </table>
        </div>
        <div class="col-md-6">
            <h6>Payment Information</h6>
            <table class="table table-sm">
                <tr><td><strong>Total Amount:</strong></td><td>₹{credit['total_amount']:.2f}</td></tr>
                <tr><td><strong>Cash Paid:</strong></td><td>₹{credit['cash_amount']:.2f}</td></tr>
                <tr><td><strong>Credit Amount:</strong></td><td>₹{credit['credit_amount']:.2f}</td></tr>
                <tr><td><strong>Amount Paid:</strong></td><td>₹{total_paid:.2f}</td></tr>
                <tr><td><strong>Remaining:</strong></td><td class="text-danger"><strong>₹{remaining_amount:.2f}</strong></td></tr>
            </table>
        </div>
    </div>
    
    <div class="row mt-3">
        <div class="col-12">
            <h6>Items Purchased</h6>
            <div class="table-responsive">
                <table class="table table-sm table-striped">
                    <thead>
                        <tr>
                            <th>Item</th>
                            <th>Category</th>
                            <th>Model</th>
                            <th>Qty</th>
                            <th>Unit Price</th>
                            <th>Total</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    
    for item in credit['sale_items']:
        html_content += f"""
                        <tr>
                            <td>{item['item_name']}</td>
                            <td>{item['category']}</td>
                            <td>{item['model_number']}</td>
                            <td>{item['quantity']}</td>
                            <td>₹{item['unit_price']:.2f}</td>
                            <td>₹{item['total_price']:.2f}</td>
                        </tr>
        """
    
    html_content += """
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """
    
    if credit.get('payment_history'):
        html_content += """
        <div class="row mt-3">
            <div class="col-12">
                <h6>Payment History</h6>
                <div class="table-responsive">
                    <table class="table table-sm table-striped">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Amount</th>
                                <th>Method</th>
                                <th>Details</th>
                                <th>Notes</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        for payment in credit['payment_history']:
            html_content += f"""
                            <tr>
                                <td>{payment['date']}</td>
                                <td>₹{payment['amount']:.2f}</td>
                                <td>{payment.get('method', 'N/A')}</td>
                                <td>{payment.get('details', 'N/A')}</td>
                                <td>{payment.get('notes', 'N/A')}</td>
                            </tr>
            """
        
        html_content += """
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        """
    
    if credit.get('description'):
        html_content += f"""
        <div class="row mt-3">
            <div class="col-12">
                <h6>Description</h6>
                <p class="text-muted">{credit['description']}</p>
            </div>
        </div>
        """
    
    return html_content

@app.route('/get_credit/<credit_id>')
@login_required
def get_credit(credit_id):
    """Get credit information for payment modal"""
    ensure_shop_folders(session['shop_name'])
    credits_data = load_credit_data()
    
    credit = next((c for c in credits_data.get('credits', []) if c['id'] == credit_id), None)
    
    if not credit:
        return jsonify({'error': 'Credit not found'}), 404
    
    # Calculate remaining amount
    total_paid = sum(payment['amount'] for payment in credit.get('payment_history', []))
    remaining_amount = credit['credit_amount'] - total_paid
    
    return jsonify({
        'id': credit['id'],
        'customer_name': credit['customer_name'],
        'customer_phone': credit['customer_phone'],
        'credit_amount': remaining_amount,
        'total_amount': credit['total_amount']
    })

@app.route('/record_payment', methods=['POST'])
@login_required
def record_payment():
    """Record a payment for a credit"""
    try:
        ensure_shop_folders(session['shop_name'])
        credits_data = load_credit_data()
        
        credit_id = request.form['credit_id']
        payment_amount = float(request.form['payment_amount'])
        payment_method = request.form['payment_method']
        payment_details = request.form.get('payment_details', '')
        payment_notes = request.form.get('payment_notes', '')
        
        # Find the credit
        credit = next((c for c in credits_data.get('credits', []) if c['id'] == credit_id), None)
        
        if not credit:
            return jsonify({'success': False, 'message': 'Credit not found'})
        
        # Calculate remaining amount
        total_paid = sum(payment['amount'] for payment in credit.get('payment_history', []))
        remaining_amount = credit['credit_amount'] - total_paid
        
        if payment_amount > remaining_amount:
            return jsonify({'success': False, 'message': 'Payment amount exceeds remaining balance'})
        
        # Add payment to history
        if 'payment_history' not in credit:
            credit['payment_history'] = []
        
        payment_record = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'amount': payment_amount,
            'method': payment_method,
            'details': payment_details,
            'notes': payment_notes
        }
        
        credit['payment_history'].append(payment_record)
        
        # Update status if fully paid
        new_total_paid = total_paid + payment_amount
        if new_total_paid >= credit['credit_amount']:
            credit['status'] = 'paid'
        
        # Save updated credit data
        save_credit_data(credits_data)
        
        # Add to daily sales for cash flow tracking
        sales_data = load_daily_data('sales')
        
        # Create a payment record in sales
        payment_sale = {
            'id': str(uuid.uuid4()),
            'customer_name': credit['customer_name'],
            'customer_phone': credit['customer_phone'],
            'item_id': 'CREDIT_PAYMENT',
            'item_name': 'Credit Payment',
            'category': 'Payment',
            'model_number': 'N/A',
            'imei_number': '',
            'quantity': 1,
            'unit_price': payment_amount,
            'total_price': payment_amount,
            'profit': 0,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'credit_payment',
            'payment_method': payment_method,
            'payment_details': payment_details,
            'credit_amount': 0,
            'cash_amount': payment_amount
        }
        
        sales_data['sales'].append(payment_sale)
        sales_data = update_daily_summary(sales_data)
        save_daily_data('sales', sales_data)
        
        return jsonify({'success': True, 'message': 'Payment recorded successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error recording payment: {str(e)}'})

# Helper functions for credit management

def load_credit_data():
    """Load credit data from credit.json"""
    shop_name = session.get('shop_name')
    if not shop_name:
        return {'credits': []}
    
    credit_file = f"data/{shop_name}/credit.json"
    
    if os.path.exists(credit_file):
        try:
            with open(credit_file, 'r', encoding='utf-8') as file:
                return json.load(file)
        except (json.JSONDecodeError, FileNotFoundError):
            return {'credits': []}
    else:
        return {'credits': []}

def save_credit_data(credits_data):
    """Save credit data to credit.json"""
    shop_name = session.get('shop_name')
    if not shop_name:
        return False
    
    credit_file = f"data/{shop_name}/credit.json"
    
    try:
        with open(credit_file, 'w', encoding='utf-8') as file:
            json.dump(credits_data, file, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving credit data: {e}")
        return False

def save_credit_transaction(customer_name, customer_phone, credit_amount, due_date, 
                          check_number, description, payment_method):
    """Save credit transaction to credit.json (used in your existing sales route)"""
    ensure_shop_folders(session['shop_name'])
    credits_data = load_credit_data()
    
    # Create new credit record
    credit_record = {
        'id': str(uuid.uuid4()),
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'customer_name': customer_name,
        'customer_phone': customer_phone,
        'total_amount': 0.0,  # Will be updated when sale items are added
        'credit_amount': credit_amount,
        'cash_amount': 0.0,   # Will be updated when sale items are added
        'due_date': due_date,
        'description': description,
        'status': 'pending',
        'sale_items': [],
        'payment_history': []
    }
    
    credits_data['credits'].append(credit_record)
    save_credit_data(credits_data)
    
    return credit_record['id']

def add_credit_record(customer_name, customer_phone, total_amount, credit_amount, 
                     due_date, description, sale_items):
    """Add or update credit record with sale items"""
    ensure_shop_folders(session['shop_name'])
    credits_data = load_credit_data()
    
    # Find existing credit record for this customer and date
    current_date = datetime.now().strftime('%Y-%m-%d')
    existing_credit = None
    
    for credit in credits_data['credits']:
        if (credit['customer_name'] == customer_name and 
            credit['customer_phone'] == customer_phone and 
            credit['date'].startswith(current_date) and
            credit['status'] == 'pending'):
            existing_credit = credit
            break
    
    if existing_credit:
        # Update existing credit
        existing_credit['total_amount'] = total_amount
        existing_credit['credit_amount'] = credit_amount
        existing_credit['cash_amount'] = total_amount - credit_amount
        existing_credit['sale_items'] = sale_items
        existing_credit['description'] = description
        existing_credit['due_date'] = due_date
    else:
        # Create new credit record
        credit_record = {
            'id': str(uuid.uuid4()),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'total_amount': total_amount,
            'credit_amount': credit_amount,
            'cash_amount': total_amount - credit_amount,
            'due_date': due_date,
            'description': description,
            'status': 'pending',
            'sale_items': sale_items,
            'payment_history': []
        }
        
        credits_data['credits'].append(credit_record)
    
    save_credit_data(credits_data)

@app.route('/credit_report')
@login_required
def credit_report():
    """Generate credit report"""
    ensure_shop_folders(session['shop_name'])
    credits_data = load_credit_data()
    
    # Calculate report data
    total_credits = len(credits_data.get('credits', []))
    total_pending_amount = 0
    total_paid_amount = 0
    overdue_credits = []
    due_soon_credits = []
    
    current_date = datetime.now().date()
    
    for credit in credits_data.get('credits', []):
        if credit['status'] == 'pending':
            total_pending_amount += credit['credit_amount']
            
            # Check if overdue or due soon
            due_date = datetime.strptime(credit['due_date'], '%Y-%m-%d').date()
            days_until_due = (due_date - current_date).days
            
            if days_until_due < 0:
                overdue_credits.append(credit)
            elif days_until_due <= 7:
                due_soon_credits.append(credit)
        else:
            # Calculate total paid from payment history
            total_paid = sum(payment['amount'] for payment in credit.get('payment_history', []))
            total_paid_amount += total_paid
    
    report_data = {
        'total_credits': total_credits,
        'total_pending_amount': total_pending_amount,
        'total_paid_amount': total_paid_amount,
        'overdue_count': len(overdue_credits),
        'due_soon_count': len(due_soon_credits),
        'overdue_credits': overdue_credits,
        'due_soon_credits': due_soon_credits,
        'all_credits': credits_data.get('credits', [])
    }
    
    return render_template('credit_report.html', report=report_data)

@app.route('/export_credits')
@login_required
def export_credits():
    """Export credits to CSV"""
    ensure_shop_folders(session['shop_name'])
    credits_data = load_credit_data()
    
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Customer Name', 'Phone', 'Date', 'Due Date', 'Total Amount', 
        'Credit Amount', 'Cash Amount', 'Status', 'Description', 'Items'
    ])
    
    # Write data
    for credit in credits_data.get('credits', []):
        items_str = '; '.join([f"{item['item_name']} ({item['quantity']}x)" 
                              for item in credit.get('sale_items', [])])
        
        writer.writerow([
            credit['customer_name'],
            credit['customer_phone'],
            credit['date'],
            credit['due_date'],
            credit['total_amount'],
            credit['credit_amount'],
            credit['cash_amount'],
            credit['status'],
            credit.get('description', ''),
            items_str
        ])
    
    output.seek(0)
    
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=credits_{datetime.now().strftime("%Y%m%d")}.csv'}
    )

@app.route('/delete_credit/<credit_id>', methods=['POST'])
@login_required
def delete_credit(credit_id):
    """Delete a credit record"""
    try:
        ensure_shop_folders(session['shop_name'])
        credits_data = load_credit_data()
        
        # Find and remove the credit
        credits_data['credits'] = [c for c in credits_data.get('credits', []) if c['id'] != credit_id]
        
        save_credit_data(credits_data)
        
        return jsonify({'success': True, 'message': 'Credit deleted successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error deleting credit: {str(e)}'})

@app.route('/update_credit_status/<credit_id>', methods=['POST'])
@login_required
def update_credit_status(credit_id):
    """Update credit status"""
    try:
        ensure_shop_folders(session['shop_name'])
        credits_data = load_credit_data()
        
        new_status = request.form.get('status')
        
        if new_status not in ['pending', 'paid']:
            return jsonify({'success': False, 'message': 'Invalid status'})
        
        # Find and update the credit
        credit = next((c for c in credits_data.get('credits', []) if c['id'] == credit_id), None)
        
        if not credit:
            return jsonify({'success': False, 'message': 'Credit not found'})
        
        credit['status'] = new_status
        
        save_credit_data(credits_data)
        
        return jsonify({'success': True, 'message': 'Status updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error updating status: {str(e)}'})

# Add this route to your main navigation or dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard with credit summary"""
    # Your existing dashboard code...
    
    # Add credit summary
    ensure_shop_folders(session['shop_name'])
    credits_data = load_credit_data()
    
    pending_credits = [c for c in credits_data.get('credits', []) if c['status'] == 'pending']
    total_pending_amount = sum(c['credit_amount'] for c in pending_credits)
    
    # Count overdue credits
    current_date = datetime.now().date()
    overdue_count = 0
    
    for credit in pending_credits:
        due_date = datetime.strptime(credit['due_date'], '%Y-%m-%d').date()
        if due_date < current_date:
            overdue_count += 1
    
    credit_summary = {
        'total_pending': len(pending_credits),
        'total_amount': total_pending_amount,
        'overdue_count': overdue_count
    }
    
    # Pass credit_summary to your dashboard template
    return render_template('dashboard.html', credit_summary=credit_summary)

@app.route('/sales2')
def sales2():
    return render_template('sales2.html')


# At the end of your app.py file, modify the main block:
if __name__ == '__main__':
    ensure_base_folders()
    # For PythonAnywhere, we don't need to specify host and port
    # PythonAnywhere handles this through WSGI
    app.run(debug=False)  # Set debug=False for production

