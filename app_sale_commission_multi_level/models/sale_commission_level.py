# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _


class SaleCommissionLevel(models.Model):
    _name = "sale.commission.level"
    _inherit = ['image.mixin']
    _description = "Sale Commission Level"

    _parent_name = "parent_id"
    _parent_store = True
    _order = 'sequence, name'

    name = fields.Char(string="Commission Level", required=True, translate=True)
    complete_name = fields.Char("Full Commission Name", compute='_compute_complete_name', store=True)
    parent_id = fields.Many2one('sale.commission.level', 'Parent Level', index=True)
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('sale.commission.level', 'parent_id', 'Child Levels')
    # 暂时所有公司可用
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True, default=lambda self: self.env.company)

    sequence = fields.Integer(string='Sequence', default=10)
    commission_user_ids = fields.Many2one(
        'sale.commission.rule',
        string="Product Template",
    )
    # 默认提成比率
    percentage = fields.Float(string='Default Rate(%)')
    # 默认加到so
    auto_add_type = fields.Selection([
        ('manual', 'Manual Set'),
        ('sales_person', 'Sales Person'),
        ('sales_person_parent', 'Parent Sales'),
        ('sales_leader', 'Sales Team Leader'),
        ('sales_partner', 'Customer')
    ], default='manual', copy=True, string='Auto Add Type')

    auto_add_leader = fields.Boolean(string='Add Sales Leader', help="Check this box to auto add Sales Team Leader to sale Commission.")
    auto_add_person = fields.Boolean(string='Add Sales 1st', help="Check this box to auto add Sales Person to sale Commission.")
    auto_add_person_parent = fields.Boolean(string='Add Sales 2nd', help="Check this box to auto add Parent Sales Person to sale Commission.")

    # 允许的类型
    is_user = fields.Boolean(string='For Internal User', default=True, help="Check this box to allow Internal User for this Commission Level.")
    supplier = fields.Boolean(string='For Vendor', help="Check this box to allow Vendor for this Commission Level.")
    customer = fields.Boolean(string='For Customer', help="Check this box to allow Customer for this Commission Level.")

    # 目录图片，可显示小图标，

    child_all_count = fields.Integer(
        'Indirect Surbordinates Count',
        compute='_compute_child_all_count', store=False)

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for rec in self:
            if rec.parent_id:
                rec.complete_name = '%s / %s' % (rec.parent_id.complete_name, rec.name)
            else:
                rec.complete_name = rec.name

    @api.depends('child_ids.child_all_count')
    def _compute_child_all_count(self):
        for rec in self:
            rec.child_all_count = len(rec.child_ids) + sum(child.child_all_count for child in rec.child_ids)
