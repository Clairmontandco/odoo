# -*- coding: utf-8 -*-

from odoo import api, models, fields

import logging
_logger = logging.getLogger(__name__)

class User(models.Model):
    _inherit = ['res.users']

    is_portal = fields.Boolean(compute='_compute_user_group', compute_sudo=True, string='Portal User', store=True)
    is_account = fields.Boolean(compute='_compute_user_group', compute_sudo=True, string='Account User', store=True)
    is_sale = fields.Boolean(compute='_compute_user_group', compute_sudo=True, string='Sale User', store=True)
    is_purchase = fields.Boolean(compute='_compute_user_group', compute_sudo=True, string='Purchase User', store=True)
    is_stock = fields.Boolean(compute='_compute_user_group', compute_sudo=True, string='Stock User', store=True)
    is_mrp = fields.Boolean(compute='_compute_user_group', compute_sudo=True, string='Mrp User', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        users = super(User, self).create(vals_list)

        for user in users:
            user.partner_id.write({
                'is_user': True,
                'related_user_id': user.id,
            })
        return users

    def write(self, vals):
        if vals.get('partner_id'):
            for rec in self.filtered(lambda r: r.partner_id.id != vals.get('partner_id')):
                # 先清旧的
                partner = self.env['res.parnter'].browse(rec.partner_id.id)
                partner.write({
                    'is_user': False,
                    'related_user_id': False,
                })
                # 再更新新的
                partner = self.env['res.parnter'].browse(vals['partner_id'])
                partner.write({
                    'is_user': True,
                    'related_user_id': rec.id,
                })
        return super(User, self).write(vals)

    def unlink(self):
        # 自动删除关联伙伴
        for rec in self:
            ids = []
            ids.append(rec.partner_id.id)
        res = super(User, self).unlink()
        try:
            self.env['res.partner'].browse(ids).unlink()
        except Exception as e:
            _logger.error('remove partner error: %s', e)
        return res

    @api.depends('groups_id')
    def _compute_user_group(self):
        for user in self:
            is_portal = user.has_group('base.group_portal')
            is_account = user.has_group('account.group_account_user')
            is_sale = user.has_group('sales_team.group_sale_salesman')
            is_purchase = user.has_group('purchase.group_purchase_user')
            is_stock = user.has_group('stock.group_stock_user')
            is_mrp = user.has_group('mrp.group_mrp_user')
            vals = {}
            if user.is_portal != is_portal:
                vals.update({'is_portal': is_portal})
            if user.is_account != is_account:
                vals.update({'is_account': is_account})
            if user.is_sale != is_sale:
                vals.update({'is_sale': is_sale})
            if user.is_purchase != is_purchase:
                vals.update({'is_purchase': is_purchase})
            if user.is_stock != is_stock:
                vals.update({'is_stock': is_stock})
            if user.is_mrp != is_mrp:
                vals.update({'is_mrp': is_mrp})
            user.update(vals)
