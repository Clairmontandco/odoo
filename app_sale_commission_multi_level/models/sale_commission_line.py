# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError, Warning


# todo: currency_id 应该用于订单实际货币，使用 company_currency_id 来做本币。  只在 invoice 时才转化到本币
# todo: 上级单为 sale order
class SaleCommissionLine(models.Model):
    _name = "sale.commission.line"
    _description = "sale.commission.line"
    _order = 'id desc'
    _rec_name = 'level_id'

    order_id = fields.Many2one('sale.order', string='Sale Order')
    name = fields.Char(string="Name", readonly=True, copy=False)
    level_id = fields.Many2one('sale.commission.level', string="Commission Level")
    user_id = fields.Many2one('res.partner', string="Internal Sales/External Agent")

    auto_add_type = fields.Selection(related='level_id.auto_add_type', readonly=True)
    # 允许的类型
    is_user = fields.Boolean(related='level_id.is_user', store=False, readonly=True)
    customer = fields.Boolean(related='level_id.customer', store=False, readonly=True)
    supplier = fields.Boolean(related='level_id.supplier', store=False, readonly=True)
    percentage = fields.Float(string='Default Rate(%)', default=0, required=True)

    currency_id = fields.Many2one(related='order_id.currency_id', store=True, string='Currency', readonly=True)
    company_id = fields.Many2one(related='order_id.company_id', string='Company', store=True, readonly=True)
    team_id = fields.Many2one(related='order_id.team_id', string='Sales Team', store=True, readonly=True)
    amount = fields.Float(string='Amount', copy=False)
    notes = fields.Text(string="Internal Notes")
    commission_product_id = fields.Many2one('product.product', string='Commission Product',
                                            domain=[('is_commission_product', '=', True)])
    # invoice_id = fields.Many2one('account.invoice', string='Account Invoice', copy=False)
    # invoice_line_id = fields.Many2one('account.invoice.line', string='Account Invoice Line', copy=False)
    # expense中删除，commission 也删除
    expense_id = fields.Many2one('hr.expense', string='Expense Line', copy=False, ondelete='cascade')
    commission_date = fields.Datetime(string='Commission Date', readonly=True, index=True, help="Date when commission confirm.")
    state = fields.Selection([
        ('no_expense', 'New'),
        ('draft', 'To Submit'),
        ('reported', 'Submitted'),
        ('approved', 'Approved'),
        ('done', 'Paid'),
        ('refused', 'Refused')
    ], compute='_compute_state', string='Status', store=False, help="Status of the expense.")
    # rule 暂时不用
    rule_id = fields.Many2one('sale.commission.rule', string="Commission Rule")

    @api.depends('expense_id')
    def _compute_state(self):
        for rec in self:
            if not rec.expense_id:
                rec.state = "no_expense"
            else:
                rec.state  = rec.expense_id.state

    @api.model
    def create(self, vals):
        if 'company_id' in vals:
            vals['name'] = self.env['ir.sequence'].with_context(force_company=vals['company_id']).next_by_code('sale.commission.line')
        else:
            vals['name'] = self.env['ir.sequence'].next_by_code('sale.commission.line')
        return super(SaleCommissionLine, self).create(vals)

    # 与expense同样处理
    def unlink(self):
        for rec in self:
            if rec.state not in ('no_expense', 'draft', 'reported'):
                raise UserError(_('Sorry! You can not delete non-draft sale commission lines!'))
        return super(SaleCommissionLine, self).unlink()

    @api.onchange('level_id')
    def _onchange_level_id(self):
        if self.level_id and self.level_id.percentage:
            self.percentage = self.level_id.percentage
        if self.level_id.auto_add_type != 'manual' and self.team_id:
            self.update({
                'user_id': False
            })

    @api.onchange('percentage')
    def _onchange_percentage(self):
        amount = 0
        percentage = self.percentage
        if percentage:
            commission_amount_on = self.order_id.commission_amount_on
            o_amount = self.order_id.amount_untaxed
            if commission_amount_on == 'amount_untaxed':
                amount =o_amount * self.percentage / 100
            else:
                for p in self.order_id.order_line:
                    try:
                        amount += self.get_commission_amount_per_soline(p.product_id, p.price_subtotal, p.product_uom_qty, p.qty_delivered, percentage)
                    except ValueError:
                        amount += 0
        self.amount = amount

    @api.model
    def get_commission_amount_per_soline(self, product=False, amount=0, product_uom_qty=0, qty_delivered=0, percentage=0):
        if amount == 0 or percentage == 0:
            return 0
        if not product:
            return amount * percentage / 100

        company = self.env.user.company_id
        product_id = self.env['ir.config_parameter'].sudo().get_param('app_commission_default_product_id')
        c_product = self.env['product.product'].browse(int(product_id))

        invoice_policy = c_product.invoice_policy
        if company.commission_amount_on == 'product_template':
            if product.is_commission_apply:
                c_amount = amount * percentage / 100
            else:
                c_amount = 0
        elif company.commission_amount_on == 'product_category':
            if product.categ_id and product.categ_id.is_commission_apply:
                c_amount = amount * percentage / 100
            else:
                c_amount = 0
        else:
            c_amount = amount * percentage / 100
        # 处理按 订单 or 交货数量
        if invoice_policy == 'delivery':
            return c_amount * qty_delivered / product_uom_qty
        else:
            return c_amount

    def create_commission_expense(self):
        product_id = self.env['ir.config_parameter'].sudo().get_param('app_commission_default_product_id')
        product = self.env['product.product'].browse(int(product_id))
        # 注意，在hr_expense中做了 default_account_id 的处理，因此要显式指定
        account = product.product_tmpl_id._get_product_accounts()['expense']
        employee_id = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        # 要检查是否已设定销售费用产品
        if not product_id:
            raise UserError(_('You muse set a product for sale commission in Sales->Configuration->Settings.'))
        exps = self.env['hr.expense']

        for commission in self:
            if not commission.expense_id:
                context = {
                    'name': '%s:%s' % (commission.order_id.name, commission.level_id.name),
                    'sale_order_id': commission.order_id.id,
                    'employee_id': int(employee_id.id),
                    'product_id': int(product_id),
                    'account_id': account.id,
                    'unit_amount': int(commission.amount),
                    'quantity': 1,
                    'date': fields.Date.context_today(self),
                    'description': '',
                    'currency_id': commission.order_id.currency_id.id,
                    'company_id': commission.order_id.company_id.id,
                    'payment_mode': 'company_account',
                    'commission_partner_id': commission.user_id.id,
                    'commission_line_id': commission.id,
                    'is_commission': True,
                }
                commission.expense_id = exps.create(context)
            exps |= commission.expense_id
        return exps
