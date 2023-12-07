# -*- coding: utf-8 -*-

from odoo import models, fields


class BankStatement(models.Model):
    _inherit = 'account.bank.statement'

    shopify_ref = fields.Char("Shopify Reference")
    shopify_payout_id = fields.Many2one('shopify.payout', string="Shopify Payout", copy=False)

    def unlink(self):
        payout_ids = self.shopify_payout_id
        res = super(BankStatement, self).unlink()
        payout_ids._compute_payout_state()
        return res


class BankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    shopify_payout_line_id = fields.Many2one('shopify.payout.line', copy=False)

    def unlink(self):
        payout_ids = self.mapped('statement_id').mapped('shopify_payout_id')
        res = super(BankStatementLine, self).unlink()
        payout_ids._compute_payout_state()
        return res
