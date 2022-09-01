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
        # Views
        'views/mrp_production_view.xml',
        'views/sale_order_view.xml',
        
        # Reports
        'reports/inherit_delivery_slip.xml',
    ],
    "auto_install": False,
    "installable": True,
    
    "price": 15,
    "currency": 'EUR',
    "category" : "Manufacturing",
    "sequence":1,
    
}
