# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import datetime
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError, ValidationError

import json


# 对预付款的处理 is_downpayment，odoo本身对预付款是不计入 amout
class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def _get_is_commission_apply(self):
        return True

    is_commission_apply = fields.Boolean(
        string='Apply Commission??',
        compute='_compute_is_commission_apply',
        default=_get_is_commission_apply
    )
    commission_rule_on = fields.Selection(related='company_id.commission_rule_on', readonly=True)
    commission_amount_on = fields.Selection(related='company_id.commission_amount_on', readonly=True)

    # 销售上线
    parent_user_id = fields.Many2one('res.users', string='2nd SalesPerson', index=True, tracking=1)
    sale_commission_line_ids = fields.One2many('sale.commission.line', 'order_id', string="Sale Commission Lines", copy=False, auto_join=True)

    # 暂时不调整，原生是有domain state=done 的
    # expense_ids = fields.One2many('hr.expense', 'sale_order_id', string='Expenses', readonly=True, copy=False)

    # 使用expense来处理，不单独用 commission
    # commission_expense_count = fields.Integer(compute="_compute_commission_expense", string='Commission Invoices Count', readonly=True, copy=False)
    # commission_expense_ids = fields.One2many("hr.expense", string='Commission Invoices', compute="_compute_commission_expense", readonly=True, copy=False)

    @api.depends('company_id')
    def _compute_is_commission_apply(self):
        for rec in self:
            self.is_commission_apply = True

    def action_view_expense(self):
        self.ensure_one()
        action = self.env.ref('hr_expense.hr_expense_actions_all').read()[0]
        action['domain'] = [('sale_order_id', '=', self.id)]
        # 默认视图改tree
        f_view = action['views'].pop(2)
        action['views'].insert(0, f_view)
        action['view_mode'] = 'tree,graph,pivot,kanban,form,activity'
        action['context'] = {
            'default_sale_order_id': self.id,
        }
        return action

    def action_create_commission_expense(self):
        '''
        生成销售费用，提成
        要考虑各种情况，主要是当该so 还有 expense 时
        '''
        self.ensure_one()
        product_id = self.env['ir.config_parameter'].sudo().get_param('app_commission_default_product_id')
        product = self.env['product.product'].browse(int(product_id))
        if not product_id:
            raise UserError(_('You muse set a product for sale commission in Sales->Configuration->Settings.'))

        sheets = self.sale_commission_line_ids.mapped('expense_id').mapped('sheet_id')
        action_vals = {
            'name': _('Commission Reports for %s') % self.name,
            'domain': [('id', 'in', sheets.ids)],
            'view_type': 'form',
            'res_model': 'hr.expense.sheet',
            'view_id': False,
            'type': 'ir.actions.act_window',
        }
        # 多张 e报告
        if len(sheets) > 1:
            action_vals['view_mode'] = 'tree,form'
            return action_vals
        # 1张 e报告
        elif len(sheets) == 1:
            action_vals.update({'res_id': sheets[0].id, 'view_mode': 'form'})
            return action_vals
        # 无 e 报告
        else:
            exps = self.sale_commission_line_ids.create_commission_expense()
            # create 报销整合单
            if len(exps):
                sheet = False
                action = exps.action_submit_expenses()
                if action.get('res_id'):
                    sheet = self.env['hr.expense.sheet'].browse(action.get('res_id'))
                    if sheet:
                        sheet.write({'name': '%s:%s' % (self.name, product.name)})
                if not sheet:
                    new_context = action.get('context', {})
                    try:
                        new_context.update({'default_name': '%s:%s' % (self.name, product.name)})
                    except Exception as e:
                        pass
                    action['context'] = new_context
                return action
            else:
                raise UserError(_('No sales commission create.'))

    @api.onchange('user_id')
    def onchange_user_id(self):
        super(SaleOrder, self).onchange_user_id()
        if self.user_id and self.user_id.user_parent_id:
            self.parent_user_id = self.user_id.user_parent_id

    def set_forecast_commission(self):
        for rec in self:
            if rec.sale_commission_line_ids:
                rec.sale_commission_line_ids.unlink()
            commission_amount_on = rec.commission_amount_on
            ids = False
            sale_commission = []
            line = self.env['sale.commission.line']
            if self.team_id and self.commission_rule_on == 'sales_team':
                ids = self.team_id.sale_commission_rule_ids
            elif self.team_id and self.commission_rule_on == 'sales_team':
                ids = self.partner_id.sale_commission_rule_ids
            if ids:
                rec.sale_commission_line_ids = None
                for rule in ids:
                    user_id = False
                    amount = 0
                    percentage = rule.percentage
                    add_type = rule.level_id.auto_add_type
                    if add_type == 'sales_person' and self.user_id:
                        user_id = self.user_id.partner_id.id
                    elif add_type == 'sales_person_parent' and self.parent_user_id:
                        user_id = self.parent_user_id.partner_id.id
                    elif add_type == 'sales_leader' and self.team_id.user_id:
                        user_id = self.team_id.user_id.partner_id.id
                    elif add_type == 'sales_partner' and self.partner_id:
                        user_id = self.partner_id.id
                    if rule.level_id and user_id:
                        if commission_amount_on == 'amount_untaxed':
                            amount = rec.amount_untaxed * percentage / 100
                        else:
                            for p in rec.order_line:
                                try:
                                    amount += line.get_commission_amount_per_soline(p.product_id, p.price_subtotal, p.product_uom_qty, p.qty_delivered, percentage)
                                except ValueError:
                                    amount += 0

                        sale_commission.append((0, 0, {'level_id': rule.level_id.id,
                                                       'user_id': user_id,
                                                       'percentage': percentage,
                                                       'currency_id': rec.currency_id.id,
                                                       'amount': amount,
                                                       'order_id': self.id}))
                rec.write({
                    'sale_commission_line_ids': sale_commission,
                })

    def action_done(self):
        res = super(SaleOrder, self).action_done()
        for rec in self:
            rec.set_forecast_commission()
        return res

    def action_cancel(self):
        res = super(SaleOrder, self).action_cancel()
        for rec in self:
            for line in self.sale_commission_line_ids:
                if line.state == 'draft' or line.state == 'cancel':
                    line.state = 'exception'
                elif line.state in ('paid', 'invoice'):
                    raise UserError(
                        _('You can not cancel this invoice because sales commission is invoiced/paid. Please cancel related commission lines and try again.'))
        return res

    def _prepare_invoice(self):
        vals = super(SaleOrder, self)._prepare_invoice()
        # if self.sale_commission_line_ids:
        #     sale_commission_lines = []
        #     for commission in self.sale_commission_line_ids:
        #         sale_commission_lines.append((0, 0, {
        #             'level_id': commission.level_id.id,
        #             'user_id': commission.user_id and commission.user_id.id or False,
        #             'percentage': commission.percentage}))
        #     vals.update({'sale_commission_line_ids': sale_commission_lines})
        return vals
