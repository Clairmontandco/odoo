# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class SaleCommissionRule(models.Model):
    _name = "sale.commission.rule"
    _description = "Sale Commission Rule"
    _rec_name = 'level_id'

    level_id = fields.Many2one(
        'sale.commission.level',
        string="Commission Level",
        required=True,
    )
    # 暂时所有公司可用
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.partner', string="Internal Sales/External Agent")
    auto_add_type = fields.Selection(related='level_id.auto_add_type', readonly=True)

    # 允许的类型
    is_user = fields.Boolean(related='level_id.is_user', store=False, readonly=True)
    customer = fields.Boolean(related='level_id.customer', store=False, readonly=True)
    supplier = fields.Boolean(related='level_id.supplier', store=False, readonly=True)
    percentage = fields.Float(string='Default Rate(%)', default=0, required=True)

    team_id = fields.Many2one('crm.team', string="Sales Team", )
    partner_id = fields.Many2one('res.partner', string="Partner")
    amount = fields.Float(string='Amount', copy=False, readonly=True)

    @api.constrains('level_id')
    def _level_validation(self):
        for level in self:
            if level.level_id:
                domain = [('level_id', '=', level.level_id.id)]
                if level.team_id:
                    domain.append(('team_id', '=', level.team_id.id))
                elif level.partner_id:
                    domain.append(('partner_id', '=', level.partner_id.id))
                level_ids = self.search_count(domain)
                if level_ids > 1:
                    raise ValidationError(_('You can not set multiple level!'))

    @api.onchange('level_id')
    def _onchange_level_id(self):
        if self.level_id and self.level_id.percentage:
            self.percentage = self.level_id.percentage
        if self.level_id.auto_add_type != 'manual' and self.team_id:
            self.update({
                'user_id': False
            })
