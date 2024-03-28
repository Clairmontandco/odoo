# -*- coding: utf-8 -*-

# Part of Probuse Consulting Service Pvt Ltd. See LICENSE file for full copyright and licensing details.

{
    'name': 'Sales Commission Multi Level for agent, customer, Internal Users.',
    'version': '15.22.01.06',
    'price': 118.0,
    'currency': 'EUR',
    'category': 'Sales',
    'author': 'odooai.cn',
    'website': 'https://www.odooai.cn',
    'license': 'LGPL-3',
    'sequence': 2,
    'summary': """
    Auto set multi level sale commission and auto calculate commission amount. Sales commision
    Sales Commission by Sales person/Sales Team/Parent Leader, to Internal Users or External Partners like Agent.
    """,
    'description': """
Sales Commission by Sales person or sale team. Auto calculate Commission amount.
Sales Commission Rule of company. how the rule affect. how to get commission amount.
Sales Commission to Internal Users and External Partners.
Sales Commission multi level rule base on sales person /sales team / customer.
Sales Commission auto Amount base on order amount / product / category.
Sales Commission workflow of expense.
Sales Commission amount auto set follow config.
    3. Multi-language Support.
    4. Multi-Company Support.
    5. Support Odoo 15,14,13,12, Enterprise and Community Edition
            """,
    'depends': [
        'app_partner_user',
        'app_users_zchart',
        'account',
        'sale_expense'
    ],
    'images': ['static/description/banner.gif'],
    'data': [
        'security/ir.model.access.csv',
        'security/sales_commission_security.xml',
        'data/commission_sequence.xml',
        'data/product_product_data.xml',
        'data/sales_commission_level_data.xml',
        'views/sale_config_settings_views.xml',
        'views/crm_team_views.xml',
        'views/res_partner_views.xml',
        'views/product_category_views.xml',
        'views/product_template_views.xml',
        'views/sale_commission_level_views.xml',
        'views/sale_commission_rule_views.xml',
        'views/sale_commission_line_views.xml',
        'views/sale_order_views.xml',
        'views/hr_expense_views.xml',
        'views/hr_expense_sheet_views.xml',
        'views/sale_commission_views.xml',
        # 'report/report_sales_commission.xml',
        # 'report/report_sales_commission_worksheet.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
}

