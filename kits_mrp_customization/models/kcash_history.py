from odoo import api,models,_,fields

class kcash_history(models.Model):
    _name = 'kcash.history'
    _description = "Kcash History"


    kcash_id = fields.Many2one('kcash.bonus',string="K-Cash")
    order_id = fields.Many2one('sale.order',string="Order")
    amount = fields.Float(string="Amount")
