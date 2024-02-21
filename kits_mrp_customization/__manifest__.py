# -*- coding: utf-8 -*-

{
    "name" : "Manufacturing Customization",
    "author": "Keypress",
    "version" : "15.0.0.0",
    "images":[],
    'summary': '',
    "description": """
    """,
    "license" : "OPL-1",
    "depends" : ['sale_management','stock','mrp','sale_mrp'],
    "data": [
        # Security
        'security/ir.model.access.csv',

        # Views
        'views/mrp_production_view.xml',
        'views/sale_order_view.xml',
        'views/stock_picking_view.xml',
        'views/sale_order_line_view.xml',
        'views/account_move_views.xml',
        'views/res_partner_view.xml',
        'views/product_product.xml',
        'views/product_category.xml',
        'views/mrp_bom_view.xml',
        
        # Data
        'data/ir_server_actions.xml',

        # Reports
        'reports/inherit_delivery_slip.xml',
        'reports/report_sale_order.xml',
        'reports/report_invoice.xml',

        # Wizards 
        'wizards/k_cash_wizard_view.xml',
        'wizards/add_k_cash_reward_wizard_view.xml',
        'wizards/create_backorder_wizard_view.xml',
        'wizards/cancel_order_wizard_view.xml'
    ],
    "auto_install": False,
    "installable": True,
    
    "price": 15,
    "currency": 'EUR',
    "category" : "Manufacturing",
    "sequence":1,
    
}
