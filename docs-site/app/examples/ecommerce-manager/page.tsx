'use client'

import React, { useState } from 'react'
import { Copy, Check, ShoppingCart, ArrowRight, ArrowLeft, Download, Play, Terminal, Lightbulb, TrendingUp, Users, DollarSign, Package } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'

const agentCode = `from connectonion import Agent
from datetime import datetime

# Global data storage
inventory = {}
orders = []
customers = {}
order_counter = 1

def manage_inventory(product_name: str, action: str, quantity: int = 0) -> str:
    """Manage product inventory - add, remove, or check stock."""
    if action == "add":
        inventory[product_name] = inventory.get(product_name, 0) + quantity
        return f"✅ Added {quantity} units of {product_name}. Current stock: {inventory[product_name]}"
    elif action == "remove":
        current = inventory.get(product_name, 0)
        if current >= quantity:
            inventory[product_name] = current - quantity
            return f"📦 Removed {quantity} units of {product_name}. Remaining: {inventory[product_name]}"
        return f"❌ Insufficient stock. Available: {current}, Requested: {quantity}"
    elif action == "check":
        stock = inventory.get(product_name, 0)
        return f"📊 {product_name}: {stock} units in stock"
    return "❌ Invalid action. Use: add, remove, or check"

def process_order(customer_name: str, product: str, quantity: int, price: float) -> str:
    """Process a new customer order."""
    global order_counter
    
    # Check inventory
    if inventory.get(product, 0) < quantity:
        return f"❌ Order failed: Insufficient stock for {product}"
    
    # Process order
    order = {
        "id": order_counter,
        "customer": customer_name,
        "product": product,
        "quantity": quantity,
        "price": price,
        "total": price * quantity,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    orders.append(order)
    inventory[product] -= quantity
    order_counter += 1
    
    return f"🎉 Order #{order['id']} processed! {customer_name} ordered {quantity}x {product} for ${'${order[\'total\']}'}"

# Create e-commerce agent
agent = Agent(
    name="ecommerce_manager",
    tools=[manage_inventory, process_order]
)`

const fullExampleCode = `# ecommerce_manager_agent.py
import os
from connectonion import Agent
from datetime import datetime, timedelta
from typing import Dict, List, Any
import json

# Set your OpenAI API key
os.environ['OPENAI_API_KEY'] = 'your-api-key-here'

# Global business data storage (use database in production)
inventory = {}
orders = []
customers = {}
analytics = {"total_revenue": 0, "total_orders": 0}
order_counter = 1
customer_counter = 1

def manage_inventory(product_name: str, action: str, quantity: int = 0, price: float = 0.0) -> str:
    """Comprehensive inventory management system."""
    try:
        if action.lower() == "add":
            if product_name not in inventory:
                inventory[product_name] = {"stock": 0, "price": price or 0.0, "sales": 0}
            
            inventory[product_name]["stock"] += quantity
            if price > 0:
                inventory[product_name]["price"] = price
                
            return f"""✅ **Inventory Updated**

📦 Product: {product_name}
➕ Added: {quantity} units
📊 Current Stock: {inventory[product_name]["stock"]} units
💰 Price: ${'${inventory[product_name]["price"]}'} each"""
        
        elif action.lower() == "remove":
            if product_name not in inventory:
                return f"❌ Product '{product_name}' not found in inventory"
                
            current_stock = inventory[product_name]["stock"]
            if current_stock >= quantity:
                inventory[product_name]["stock"] -= quantity
                return f"""📦 **Stock Removed**

📦 Product: {product_name}
➖ Removed: {quantity} units
📊 Remaining Stock: {inventory[product_name]["stock"]} units"""
            else:
                return f"❌ **Insufficient Stock**\\n\\n📦 Product: {product_name}\\n📊 Available: {current_stock} units\\n❌ Requested: {quantity} units"
        
        elif action.lower() == "check":
            if product_name == "all":
                if not inventory:
                    return "📦 **Inventory Empty**\\n\\nNo products currently in stock."
                
                result = "📊 **Complete Inventory Report**\\n\\n"
                total_value = 0
                for product, data in inventory.items():
                    stock_value = data["stock"] * data["price"]
                    total_value += stock_value
                    status = "🟢 In Stock" if data["stock"] > 10 else ("🟡 Low Stock" if data["stock"] > 0 else "🔴 Out of Stock")
                    result += f"📦 **{product}**\\n   • Stock: {data['stock']} units\\n   • Price: ${'${data[\"price\"]}'}\\n   • Value: ${'${stock_value}'}\\n   • Sales: {data['sales']} units sold\\n   • Status: {status}\\n\\n"
                
                result += f"💰 **Total Inventory Value: ${'${total_value}'}**"
                return result
            else:
                if product_name in inventory:
                    data = inventory[product_name]
                    stock_value = data["stock"] * data["price"]
                    status = "🟢 In Stock" if data["stock"] > 10 else ("🟡 Low Stock" if data["stock"] > 0 else "🔴 Out of Stock")
                    
                    return f"""📊 **Product Details: {product_name}**

📦 Stock: {data["stock"]} units
💰 Price: ${'${data["price"]}'} each  
📈 Total Sales: {data["sales"]} units sold
💵 Current Value: ${'${stock_value}'}
🚦 Status: {status}"""
                else:
                    available = list(inventory.keys())
                    return f"❌ Product '{product_name}' not found.\\n\\n📦 Available products: {', '.join(available) or 'None'}"
        
        elif action.lower() == "update_price":
            if product_name in inventory:
                old_price = inventory[product_name]["price"]
                inventory[product_name]["price"] = price
                return f"💰 **Price Updated**\\n\\n📦 Product: {product_name}\\n💵 Old Price: ${'${old_price}'}\\n💰 New Price: ${'${price}'}"
            else:
                return f"❌ Product '{product_name}' not found in inventory"
        
        else:
            return "❌ **Invalid Action**\\n\\nValid actions: add, remove, check, update_price\\nExample: 'Add 50 laptops to inventory with price 999.99'"
    
    except Exception as e:
        return f"❌ **Inventory Error**: {str(e)}"

def process_order(customer_name: str, customer_email: str, product: str, quantity: int) -> str:
    """Process customer orders with full business logic."""
    global order_counter
    
    try:
        # Validate inventory
        if product not in inventory:
            available = list(inventory.keys())
            return f"❌ **Product Not Available**\\n\\n📦 '{product}' is not in our catalog\\n\\n🛍️ Available products: {', '.join(available) or 'None'}"
        
        product_data = inventory[product]
        if product_data["stock"] < quantity:
            return f"""❌ **Insufficient Stock**

📦 Product: {product}
📊 Available: {product_data["stock"]} units
❌ Requested: {quantity} units
💡 Suggestion: Reduce quantity or restock inventory"""
        
        # Calculate order details
        unit_price = product_data["price"]
        subtotal = unit_price * quantity
        tax_rate = 0.08  # 8% tax
        tax = subtotal * tax_rate
        total = subtotal + tax
        
        # Create order
        order = {
            "id": order_counter,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "product": product,
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": subtotal,
            "tax": tax,
            "total": total,
            "status": "confirmed",
            "date": datetime.now().isoformat(),
            "estimated_delivery": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        }
        
        # Update inventory and records
        inventory[product]["stock"] -= quantity
        inventory[product]["sales"] += quantity
        orders.append(order)
        
        # Update customer records
        if customer_email not in customers:
            global customer_counter
            customers[customer_email] = {
                "id": customer_counter,
                "name": customer_name,
                "email": customer_email,
                "orders": [],
                "total_spent": 0,
                "registration_date": datetime.now().isoformat()
            }
            customer_counter += 1
        
        customers[customer_email]["orders"].append(order_counter)
        customers[customer_email]["total_spent"] += total
        
        # Update analytics
        analytics["total_revenue"] += total
        analytics["total_orders"] += 1
        
        order_counter += 1
        
        return f"""🎉 **Order Confirmed!**

📋 **Order Details:**
• Order ID: #{order['id']}
• Customer: {customer_name} ({customer_email})
• Product: {product}
• Quantity: {quantity} units
• Unit Price: ${'${unit_price}'}

💰 **Pricing:**
• Subtotal: ${'${subtotal}'}
• Tax (8%): ${'${tax}'}
• **Total: ${'${total}'}**

📦 **Fulfillment:**
• Status: Confirmed
• Estimated Delivery: {order['estimated_delivery']}
• Remaining Stock: {inventory[product]['stock']} units

Thank you for your order! 🚚"""
    
    except Exception as e:
        return f"❌ **Order Processing Error**: {str(e)}"

def get_business_analytics() -> str:
    """Generate comprehensive business analytics and insights."""
    try:
        if not orders:
            return "📊 **Business Analytics**\\n\\nNo orders processed yet. Start by processing some orders to see analytics!"
        
        # Revenue analytics
        total_revenue = analytics["total_revenue"]
        total_orders = len(orders)
        avg_order_value = total_revenue / total_orders or 0
        
        # Product performance
        product_sales = {}
        product_revenue = {}
        for order in orders:
            product = order["product"]
            product_sales[product] = product_sales.get(product, 0) + order["quantity"]
            product_revenue[product] = product_revenue.get(product, 0) + order["total"]
        
        # Top products
        top_selling = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:3]
        top_revenue = sorted(product_revenue.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # Customer analytics
        total_customers = len(customers)
        customer_spending = []
        for customer_data in customers.values():
            customer_spending.append(customer_data["total_spent"])
        
        avg_customer_value = sum(customer_spending) / len(customer_spending) or 0
        
        # Inventory value
        inventory_value = sum(data["stock"] * data["price"] for data in inventory.values())
        
        # Recent orders (last 5)
        recent_orders = sorted(orders, key=lambda x: x["date"], reverse=True)[:5]
        
        result = f"""📊 **Business Analytics Dashboard**

💰 **Financial Overview:**
• Total Revenue: ${'${total_revenue}'}
• Total Orders: {total_orders}
• Average Order Value: ${'${avg_order_value}'}
• Total Customers: {total_customers}
• Average Customer Value: ${'${avg_customer_value}'}

🏆 **Top Performing Products (by units sold):**"""
        
        for i, (product, sales) in enumerate(top_selling, 1):
            result += f"\\n{i}. {product}: {sales} units sold"
        
        result += "\\n\\n💵 **Top Revenue Generators:**"
        for i, (product, revenue) in enumerate(top_revenue, 1):
            result += f"\\n{i}. {product}: ${'${revenue}'} revenue"
        
        result += f"""

📦 **Inventory Status:**
• Total Inventory Value: ${'${inventory_value}'}
• Products in Catalog: {len(inventory)}

📈 **Recent Activity:**"""
        
        for order in recent_orders:
            result += f"\\n• Order #{order['id']}: {order['customer_name']} - {order['product']} (${'${order[\"total\"]}'})"
        
        return result
    
    except Exception as e:
        return f"❌ **Analytics Error**: {str(e)}"

def manage_customers(action: str, email: str = "", name: str = "") -> str:
    """Customer relationship management."""
    try:
        if action.lower() == "list":
            if not customers:
                return "👥 **Customer Database**\\n\\nNo customers registered yet."
            
            result = f"👥 **Customer Database** ({len(customers)} customers)\\n\\n"
            for customer_data in customers.values():
                order_count = len(customer_data["orders"])
                result += f"👤 **{customer_data['name']}**\\n   • Email: {customer_data['email']}\\n   • Orders: {order_count}\\n   • Total Spent: ${'${customer_data[\"total_spent\"]}'}\\n   • Member Since: {customer_data['registration_date'][:10]}\\n\\n"
            
            return result
        
        elif action.lower() == "lookup":
            if email in customers:
                customer = customers[email]
                order_history = ""
                for order_id in customer["orders"]:
                    order = next((o for o in orders if o["id"] == order_id), None)
                    if order:
                        order_history += f"\\n   • Order #{order_id}: {order['product']} x{order['quantity']} (${'${order[\"total\"]}'}) - {order['date'][:10]}"
                
                return f"""👤 **Customer Profile**

📧 Email: {customer["email"]}
👤 Name: {customer["name"]}
📅 Member Since: {customer["registration_date"][:10]}
🛍️ Total Orders: {len(customer["orders"])}
💰 Total Spent: ${'${customer["total_spent"]}'}

📋 **Order History:**{order_history or "\\n   • No orders yet"}"""
            else:
                return f"❌ Customer with email '{email}' not found in database."
        
        else:
            return "❌ **Invalid Action**\\n\\nValid actions: list, lookup\\nExample: 'Look up customer john@example.com'"
    
    except Exception as e:
        return f"❌ **Customer Management Error**: {str(e)}"

def generate_report(report_type: str) -> str:
    """Generate various business reports."""
    try:
        if report_type.lower() == "daily":
            today = datetime.now().date()
            today_orders = [o for o in orders if datetime.fromisoformat(o["date"]).date() == today]
            daily_revenue = sum(order["total"] for order in today_orders)
            
            return f"""📅 **Daily Report - {today}**

📊 **Today's Performance:**
• Orders: {len(today_orders)}
• Revenue: ${'${daily_revenue}'}
• Average Order: ${'${daily_revenue}'}

🛍️ **Order Details:**"""
            
        elif report_type.lower() == "inventory":
            low_stock_items = [(name, data) for name, data in inventory.items() if data["stock"] < 10]
            out_of_stock = [(name, data) for name, data in inventory.items() if data["stock"] == 0]
            
            result = f"""📦 **Inventory Report**

⚠️  **Attention Required:**
• Low Stock Items: {len(low_stock_items)}
• Out of Stock Items: {len(out_of_stock)}

📊 **Stock Status:**"""
            
            if low_stock_items:
                result += "\\n\\n🟡 **Low Stock (< 10 units):**"
                for name, data in low_stock_items:
                    result += f"\\n• {name}: {data['stock']} units remaining"
            
            if out_of_stock:
                result += "\\n\\n🔴 **Out of Stock:**"
                for name, data in out_of_stock:
                    result += f"\\n• {name}: URGENT - Restock needed!"
            
            return result
        
        else:
            return "❌ **Invalid Report Type**\\n\\nAvailable reports: daily, inventory\\nExample: 'Generate daily report'"
    
    except Exception as e:
        return f"❌ **Report Generation Error**: {str(e)}"

# Create the comprehensive e-commerce management agent
agent = Agent(
    name="ecommerce_manager",
    system_prompt="""You are an expert e-commerce business manager with comprehensive capabilities:

🛍️ **Core Functions:**
• Inventory Management: Add, remove, check stock, update prices
• Order Processing: Handle customer orders with full business logic  
• Customer Management: Track customer relationships and history
• Business Analytics: Revenue, sales, and performance insights
• Reporting: Daily, inventory, and custom business reports

💼 **Business Expertise:**
• Calculate taxes, totals, and delivery estimates
• Identify low stock and reorder opportunities  
• Track customer lifetime value and order patterns
• Provide actionable business insights and recommendations
• Maintain professional customer service standards

🎯 **Communication Style:**
• Professional yet friendly business communication
• Clear, actionable information with proper formatting
• Proactive suggestions for business optimization
• Detailed explanations of business metrics and KPIs

Always focus on helping grow and optimize the e-commerce business!""",
    tools=[manage_inventory, process_order, get_business_analytics, manage_customers, generate_report]
)

if __name__ == "__main__":
    print("=== E-commerce Manager Agent Demo ===\\n")
    
    # Demo business workflow
    demo_commands = [
        "Add 100 laptops to inventory with price 999.99",
        "Add 50 wireless mice to inventory with price 29.99", 
        "Add 75 keyboards to inventory with price 79.99",
        "Process order for John Smith (john@email.com): 2 laptops",
        "Process order for Sarah Johnson (sarah@email.com): 5 wireless mice and 2 keyboards",
        "Check inventory status for all products",
        "Show me business analytics",
        "List all customers",
        "Generate inventory report"
    ]
    
    for i, command in enumerate(demo_commands, 1):
        print(f"Command {i}: {command}")
        response = agent.input(command)
        print(f"Response: {response}\\n")
        print("-" * 80)`

export default function EcommerceManagerPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# E-commerce Manager Agent - ConnectOnion Tutorial

Learn complex business logic, multi-agent coordination, and enterprise-grade workflow automation by building a comprehensive e-commerce management system.

## What You'll Learn

- Complex business logic implementation
- Multi-system coordination and data flow
- Enterprise-grade error handling and validation
- Customer relationship management (CRM) patterns
- Business analytics and reporting systems
- Professional communication and formatting

## Key Features

- 🛍️ Complete inventory management system with stock tracking and pricing
- 📋 Full order processing with tax calculation and delivery estimates
- 👥 Customer relationship management with purchase history
- 📊 Comprehensive business analytics and performance metrics
- 📈 Multiple report generation (daily, inventory, custom)
- 💰 Revenue tracking and business intelligence
- ⚡ Real-time stock management and alerts

## Complete Example

\`\`\`python
${fullExampleCode}
\`\`\`

## Enterprise Concepts

This example demonstrates:
- **Business Logic**: Tax calculations, delivery estimates, and workflow automation
- **Data Relationships**: Orders, customers, and inventory working together
- **Analytics & Reporting**: Business intelligence and performance tracking
- **Professional Communication**: Structured output and business-appropriate messaging
- **Scalable Architecture**: Design patterns that work for enterprise applications

Perfect foundation for building complex business and enterprise agents!`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/examples" className="hover:text-white transition-colors">Agent Building</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">E-commerce Manager</span>
      </nav>

      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-emerald-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">8</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <ShoppingCart className="w-8 h-8 text-emerald-400" />
                <h1 className="text-4xl font-bold text-white">E-commerce Manager Agent</h1>
                <span className="px-3 py-1 bg-emerald-900/50 text-emerald-300 rounded-full text-sm font-medium">
                  Expert
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Learn complex business logic and enterprise-grade workflow automation with a comprehensive e-commerce management system.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="ecommerce-manager-agent.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      <div className="mb-12 p-6 bg-emerald-900/20 border border-emerald-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-emerald-400" />
          What You'll Learn
        </h2>
        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-emerald-600 rounded-lg flex items-center justify-center">
              <Package className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Business Logic</h3>
            <p className="text-emerald-200 text-sm">Complex workflows and calculations</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-emerald-600 rounded-lg flex items-center justify-center">
              <Users className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">CRM Systems</h3>
            <p className="text-emerald-200 text-sm">Customer relationship management</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-emerald-600 rounded-lg flex items-center justify-center">
              <TrendingUp className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Analytics</h3>
            <p className="text-emerald-200 text-sm">Business intelligence and reporting</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-emerald-600 rounded-lg flex items-center justify-center">
              <DollarSign className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Revenue Tracking</h3>
            <p className="text-emerald-200 text-sm">Financial metrics and optimization</p>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-12">
        {/* Code Examples */}
        <div className="space-y-8">
          {/* Basic Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Basic E-commerce Manager</h3>
              <button
                onClick={() => copyToClipboard(agentCode, 'basic')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'basic' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6 ">
              <SyntaxHighlighter 
                language="python" 
                style={vscDarkPlus}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {agentCode}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Complete Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Enterprise E-commerce Manager</h3>
              <button
                onClick={() => copyToClipboard(fullExampleCode, 'complete')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'complete' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6 ">
              <SyntaxHighlighter 
                language="python" 
                style={vscDarkPlus}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {fullExampleCode}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="space-y-8">
          {/* Output */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
              <Terminal className="w-5 h-5 text-emerald-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm ">
                <pre className="text-emerald-200 whitespace-pre-wrap">
                  {`=== E-commerce Manager Agent Demo ===

Command 1: Add 100 laptops to inventory with price 999.99
Response: ✅ **Inventory Updated**

📦 Product: laptops
➕ Added: 100 units
📊 Current Stock: 100 units
💰 Price: $999.99 each

Command 4: Process order for John Smith (john@email.com): 2 laptops
Response: 🎉 **Order Confirmed!**

📋 **Order Details:**
• Order ID: #1
• Customer: John Smith (john@email.com)
• Product: laptops
• Quantity: 2 units
• Unit Price: $999.99

💰 **Pricing:**
• Subtotal: $1999.98
• Tax (8%): $159.98
• **Total: $2159.96**

📦 **Fulfillment:**
• Status: Confirmed
• Estimated Delivery: 2024-03-18
• Remaining Stock: 98 units

Command 7: Show me business analytics
Response: 📊 **Business Analytics Dashboard**

💰 **Financial Overview:**
• Total Revenue: $2759.89
• Total Orders: 2
• Average Order Value: $1379.95
• Total Customers: 2
• Average Customer Value: $1379.95

🏆 **Top Performing Products (by units sold):**
1. wireless mice: 5 units sold
2. laptops: 2 units sold
3. keyboards: 2 units sold`}
                </pre>
              </div>
            </div>
          </div>

          {/* Enterprise Patterns */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">Enterprise Patterns</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-emerald-400 mb-2">🏢 Business Logic</h4>
                <p className="text-gray-300">Complex workflows with tax calculations, delivery estimates, and multi-system coordination.</p>
              </div>
              <div>
                <h4 className="font-semibold text-emerald-400 mb-2">🔄 Data Relationships</h4>
                <p className="text-gray-300">Orders, customers, and inventory working together with referential integrity.</p>
              </div>
              <div>
                <h4 className="font-semibold text-emerald-400 mb-2">📊 Business Intelligence</h4>
                <p className="text-gray-300">Real-time analytics, performance metrics, and actionable business insights.</p>
              </div>
            </div>
          </div>

          {/* Features */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Enterprise Features</h3>
            <div className="space-y-3 text-sm">
              <div className="p-3 bg-emerald-900/20 border border-emerald-500/30 rounded">
                <p className="text-emerald-300 font-medium mb-1">🛍️ Order Management</p>
                <p className="text-emerald-200">Complete order lifecycle with tax calculation and delivery tracking</p>
              </div>
              <div className="p-3 bg-emerald-900/20 border border-emerald-500/30 rounded">
                <p className="text-emerald-300 font-medium mb-1">👥 CRM Integration</p>
                <p className="text-emerald-200">Customer profiles, purchase history, and lifetime value tracking</p>
              </div>
              <div className="p-3 bg-emerald-900/20 border border-emerald-500/30 rounded">
                <p className="text-emerald-300 font-medium mb-1">📈 Advanced Analytics</p>
                <p className="text-emerald-200">Revenue tracking, product performance, and business intelligence reports</p>
              </div>
            </div>
          </div>

          {/* Download */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Try It Yourself</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(fullExampleCode)}`}
                download="ecommerce_manager_agent.py"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Complete Example
              </a>
              <p className="text-xs text-gray-400 text-center">
                Enterprise-grade e-commerce system with full business logic and analytics
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Previous in series</p>
          <Link 
            href="/examples/api-client" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            7. API Client
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Complete!</p>
          <Link 
            href="/examples" 
            className="flex items-center gap-2 text-emerald-400 hover:text-emerald-300 transition-colors font-medium"
          >
            View All Examples
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}