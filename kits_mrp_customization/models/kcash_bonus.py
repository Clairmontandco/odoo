from odoo import api,models,_,fields

class kcash_bonus(models.Model):
    _name = 'kcash.bonus'
    _description = "Kcash Bonus"
    _rec_name = "sale_id"

    partner_id = fields.Many2one('res.partner','Partner ID')
    sale_id = fields.Many2one('sale.order','Order')
    credit = fields.Float('Amount')
    debit = fields.Float('Debit Amount')
    balance = fields.Float('Balance',compute='_compute_balance_amount',store=True)
    expiry_date = fields.Date('Expiry Date',default=fields.Date.today())
    reward_fullfill = fields.Boolean()
    domain_order_ids = fields.Many2many("sale.order",'kcashbonus_saleorder_rel','kcash_bonus_id','sale_order_id','Domain Order Ids',compute="_compute_domain_sale_order",store=True)
    kcash_type = fields.Selection([('reward','Reward'),('credit','Credit')],default='reward',string='Type')

    @api.depends('debit','credit')
    def _compute_balance_amount(self):
        for rec in self:
            rec.balance = rec.credit - rec.debit
            if rec.credit == rec.debit:
                rec.reward_fullfill = True

    @api.model
    def default_get(self,fields):
        fields.append('partner_id')
        rec = super(kcash_bonus, self).default_get(fields)
        return rec

    @api.depends('sale_id','kcash_type')
    def _compute_domain_sale_order(self):
        for rec in self:
            order_ids = rec.partner_id.kcash_bonus_ids.mapped('sale_id').ids
            if rec.kcash_type == 'reward':
                rec.write({
                    'domain_order_ids' : [(6,0,order_ids)]
                })
            else:
                rec.domain_order_ids = None

    @api.onchange('kcash_type')
    def onchange_kcash_type(self):
        for rec in self:
            if (rec.kcash_type == 'reward') and (rec.sale_id.id in rec.domain_order_ids.ids):
                rec.sale_id = None