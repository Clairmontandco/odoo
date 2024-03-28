# -*- coding: utf-8 -*-

# Created on 2017-11-22
# author: 欧度智能，http://www.odooai.cn
# email: 300883@qq.com
# resource of odooai
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Odoo在线中文用户手册（长期更新）
# http://www.odooai.cn/documentation/user/10.0/zh_CN/index.html

# Odoo10离线中文用户手册下载
# http://www.odooai.cn/odoo10_user_manual_document_offline/
# Odoo10离线开发手册下载-含python教程，jquery参考，Jinja2模板，PostgresSQL参考（odoo开发必备）
# http://www.odooai.cn/odoo10_developer_document_offline/
# description:

from odoo import api, SUPERUSER_ID, _

def pre_init_hook(cr):
    """
    数据初始化，只在安装时执行，更新时不执行
    """
    try:
        env = api.Environment(cr, SUPERUSER_ID, {})
        # 找到主公司，更新sale team
        c = env.ref('base.main_company')
        if c:
            teams = env['crm.team'].sudo().search([
                        ('company_id', '=', False)
                    ])
            teams.write({
                'company_id': c.id,
            })

        # # 配置默认值
        # vlist = [{
        #     'key': 'app_sale_commission_multi_level.commission_rule_on',
        #     'value': 'sales_team',
        # }, {
        #     'key': 'app_sale_commission_multi_level.commission_amount_on',
        #     'value': 'amount_untaxed',
        # }, {
        #     'key': 'app_sale_commission_multi_level.default_commission_invoice_policy',
        #     'value': 'order',
        # }]
        # for v in vlist:
        #     p = env['ir.config_parameter'].sudo().search([('key', 'like', v['key'])])
        #     if p:
        #         p.write(v)
        #     else:
        #         p.create(v)
    except Exception as e:
        pass

def post_init_hook(cr, registry):
    """
    数据初始化，只在安装后执行，更新时不执行
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    ids = env['sale.commission.level'].sudo().with_context(lang='zh_CN').search([
                ('parent_id', '=', False)
            ])
    ids._compute_complete_name()

