from odoo import models
# from odoo.exceptions import UserError

class sale_advance_payment_inv(models.TransientModel):
    _inherit='sale.advance.payment.inv'

    def _create_invoice(self, order, so_line, amount):
        invoice = super(sale_advance_payment_inv, self)._create_invoice(order=order,so_line=so_line,amount=amount)
        invoice.sale_order_id = order.id
        return invoice