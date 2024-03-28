# -*- coding: utf-8 -*-

# Created on 2018-11-26
# author: 欧度智能，https://www.odooai.cn
# email: 300883@qq.com
# resource of odooai
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

# Odoo12在线用户手册（长期更新）
# https://www.odooai.cn/documentation/user/12.0/zh_CN/index.html

# Odoo12在线开发者手册（长期更新）
# https://www.odooai.cn/documentation/12.0/index.html

# Odoo10在线中文用户手册（长期更新）
# https://www.odooai.cn/documentation/user/10.0/zh_CN/index.html

# Odoo10离线中文用户手册下载
# https://www.odooai.cn/odoo10_user_manual_document_offline/
# Odoo10离线开发手册下载-含python教程，jquery参考，Jinja2模板，PostgresSQL参考（odoo开发必备）
# https://www.odooai.cn/odoo10_developer_document_offline/
# description:

{
    'name': "App Partner User related,User Type",
    'version': '15.23.02.10',
    'author': 'odooai.cn',
    'category': 'Base',
    'website': 'https://www.odooai.cn',
    'license': 'LGPL-3',
    'sequence': 2,
    'price': 38.00,
    'currency': 'EUR',
    'images': ['static/description/banner.png'],
    'depends': [
        'account',
        'sale',
        'purchase',
        'stock',
        'mrp',
    ],
    'summary': """
    Add partner user related fields on partner and add them in partner view.
    partner relate user. partner is user. Add user filter for partner views.
    Auto delete related partner when user deleted.
    """,
    'description': """
    Filter odoo user in partner view.
    Filter odoo user of follow category.
    Portal User, Account User, Sale User, Purchase User, Stock User, Mrp User
    模块开发模板，目录结构与文件定义。
    """,
    'data': [
        'views/res_partner_views.xml',
        'views/res_users_views.xml',
    ],
    'qweb': [
        'static/src/xml/*.xml',
    ],
    'demo': [],
    'test': [],
    'css': [],
    'js': [],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}
