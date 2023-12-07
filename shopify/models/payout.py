import pytz
import logging
from .. import shopify
import urllib.parse as urlparse
from odoo import models, fields, api, registry, _
from odoo.exceptions import UserError
from datetime import timedelta, datetime
from .misc import convert_shopify_datetime_to_utc

_logger = logging.getLogger("Teqstars:Shopify-Payout")

PAYOUT_TRANSACTION_TYPE = [('charge', 'Charge'),
                           ('refund', 'Refund'),
                           ('dispute', 'Dispute'),
                           ('reserve', 'Reserve'), ('adjustment', 'Adjustment'),
                           ('credit', 'Credit'),
                           ('debit', 'Debit'), ('payout', 'Payout'),
                           ('payout_failure', 'Payout Failure'),
                           ('refund_failure', 'Refund Failure'),
                           ('payment_refund', 'Payment Refund'),
                           ('payout_cancellation', 'Payout Cancellation'), ('fees', 'Fees')]

INVOICE_AND_PAYMENT_TYPES = {
    'charge': {'invoice_type': 'out_invoice', 'payment_type': 'inbound'},
    'refund': {'invoice_type': 'out_refund', 'payment_type': 'outbound'},
    'payment_refund': {'invoice_type': 'out_refund', 'payment_type': 'outbound'}}


class ShopifyPayout(models.Model):
    _name = "shopify.payout"
    _description = "Shopify Payout"
    _order = 'payout_date desc'

    @api.depends('bank_statement_id', 'bank_statement_id.state')
    def _compute_payout_state(self):
        for record in self:
            if not record.bank_statement_id:
                record.state = 'draft'
            else:
                record.state = 'draft' if record.bank_statement_id.state == 'open' else record.bank_statement_id.state

    @api.depends('payout_line_ids.is_reconciled')
    def _compute_all_lines_reconciled(self):
        for payout in self:
            payout.all_lines_reconciled = all(payout_line.is_reconciled for payout_line in payout.payout_line_ids)

    name = fields.Char('Name', required=True, copy=False, index=True, default=lambda self: _('New'))
    report_id = fields.Char("Shopify Payout ID", copy=False)
    mk_instance_id = fields.Many2one('mk.instance', "Instance", copy=False)
    state = fields.Selection([('draft', 'Draft'), ('posted', 'Processing'), ('confirm', 'Validated')], string="Status", default="draft", compute="_compute_payout_state", store=True)
    currency_id = fields.Many2one('res.currency', string="Currency", copy=False)
    payout_date = fields.Date("Payout Date", help="The date when the payout was issued.")
    payout_line_ids = fields.One2many('shopify.payout.line', 'payout_id')
    amount = fields.Float("Amount", help="The total amount of the payout.")
    bank_statement_id = fields.Many2one('account.bank.statement', string="Statement")
    all_lines_reconciled = fields.Boolean(compute='_compute_all_lines_reconciled', help="Technical field indicating if all payout lines are fully reconciled.")

    # For to search payout based on order number or order ID.
    order_id = fields.Many2one(related="payout_line_ids.order_id")
    source_order_id = fields.Char(related="payout_line_ids.source_order_id")

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('shopify.payout') or _('New')
        res = super(ShopifyPayout, self).create(vals)
        return res

    def fetch_payout_from_shopify(self, mk_instance_id, from_date=False, to_date=False):
        if not from_date:
            from_date = mk_instance_id.payout_report_last_sync_date if mk_instance_id.payout_report_last_sync_date else fields.Date.today() - timedelta(days=30)
        if not to_date:
            to_date = fields.Date.today()
        mk_instance_id.connection_to_shopify()
        payout_list, page_info = [], False
        while 1:
            if page_info:
                page_wise_payout_list = shopify.Payouts().find(limit=mk_instance_id.api_limit, page_info=page_info)
            else:
                page_wise_payout_list = shopify.Payouts().find(status="paid", date_min=from_date, date_max=to_date, limit=mk_instance_id.api_limit)
            page_url = page_wise_payout_list.next_page_url
            parsed = urlparse.parse_qs(page_url)
            page_info = parsed.get('page_info', False) and parsed.get('page_info', False)[0] or False
            payout_list += page_wise_payout_list
            if not page_info:
                break
        return payout_list, from_date, to_date

    def fetch_transaction_of_payout(self, payout_id):
        payout_transaction_list, page_info, limit = [], False, 250
        payout_list, page_info = [], False
        while 1:
            if page_info:
                page_wise_transaction_list = shopify.Transactions().find(limit=limit, page_info=page_info)
            else:
                page_wise_transaction_list = shopify.Transactions().find(payout_id=payout_id, limit=limit)
            page_url = page_wise_transaction_list.next_page_url
            parsed = urlparse.parse_qs(page_url)
            page_info = parsed.get('page_info', False) and parsed.get('page_info', False)[0] or False
            payout_transaction_list += page_wise_transaction_list
            if not page_info:
                break
        return payout_transaction_list

    def view_bank_statement(self):
        self.ensure_one()
        result = self.env['ir.actions.act_window']._for_xml_id('account.action_bank_statement_tree')
        form = self.env.ref('account.view_bank_statement_form', False)
        form_view = [(form.id if form else False, 'form')]
        if 'views' in result:
            result['views'] = form_view + [(state, view) for state, view in result['views'] if view != 'form']
        else:
            result['views'] = form_view
        result['res_id'] = self.bank_statement_id.id
        return result

    def prepare_bank_statement_line_vals(self, payout_line_id, order_id):
        self.ensure_one()
        partner_id = self.env['res.partner']
        payout_currency = self.currency_id
        journal_currency = self.mk_instance_id.payout_journal_id.currency_id or self.mk_instance_id.payout_journal_id.company_id.currency_id
        if order_id:
            partner_id = self.env['res.partner']._find_accounting_partner(order_id.partner_id)
        vals = {
            'name': payout_line_id.transaction_label or payout_line_id.transaction_id,
            'payment_ref': payout_line_id.transaction_label,
            'ref': payout_line_id.transaction_id,
            'amount': payout_currency._convert(payout_line_id.amount, journal_currency, self.mk_instance_id.payout_journal_id.company_id, self.payout_date),
            'date': self.payout_date,
            'partner_id': partner_id.id or False,
            'currency_id': self.mk_instance_id.payout_journal_id.currency_id.id or self.mk_instance_id.payout_journal_id.company_id.currency_id.id,
            'shopify_payout_line_id': payout_line_id.id,
            'sequence': 1000,
        }
        if payout_currency != journal_currency:
            vals.update({'foreign_currency_id': self.currency_id.id, 'amount_currency': payout_line_id.amount, })
        return vals

    def prepare_bank_statement_line(self, statement_id=False):
        self.ensure_one()
        bank_statement_line_list = []
        for payout_line_id in self.payout_line_ids.filtered(lambda x: not x.bank_statement_line_id):
            order_id = payout_line_id.order_id
            existing_statement_line = False
            if not order_id and payout_line_id.source_order_id:
                order_id = self.env['sale.order'].search([('mk_id', '=', payout_line_id.source_order_id), ('mk_instance_id', '=', self.mk_instance_id.id)], limit=1)
                if order_id:
                    payout_line_id.write({'source_order_id': order_id.id})
            if statement_id and payout_line_id.transaction_id:
                existing_statement_line = statement_id.line_ids.filtered(lambda x: x.ref == payout_line_id.transaction_id)
            if payout_line_id.transaction_type in ['charge', 'refund', 'payment_refund'] and not order_id:
                payout_line_id.write({'warn_message': "Order not found : Transaction won't reconcile automatically."})
            elif payout_line_id.transaction_type in ['charge', 'refund', 'payment_refund']:
                transaction_amount = payout_line_id.amount if payout_line_id.transaction_type == 'charge' else -payout_line_id.amount
                invoice_ids = order_id.invoice_ids.filtered(lambda x: x.state == 'posted' and x.move_type == INVOICE_AND_PAYMENT_TYPES[payout_line_id.transaction_type]['invoice_type'])

                if invoice_ids and sum(invoice_ids.mapped('amount_total')) != transaction_amount:
                    payout_line_id.write({'warn_message': "Invoice amount mismatch. Please try to reconcile manually."})

                if not invoice_ids:
                    payout_line_id.write(
                        {'warn_message': "Invoice not found: Invoice isn't created for order {} for transaction type {}.".format(order_id.name, payout_line_id.transaction_type)})
            if statement_id and payout_line_id.transaction_type == 'fees':
                existing_statement_line = statement_id.line_ids.filtered(lambda x: x.payment_ref == payout_line_id.transaction_label)
            if existing_statement_line:
                existing_statement_line.write({'shopify_payout_line_id': payout_line_id.id, 'payment_ref': payout_line_id.transaction_label, 'name': payout_line_id.transaction_label or payout_line_id.transaction_id})
                continue
            bank_statement_line_list.append((0, 0, self.prepare_bank_statement_line_vals(payout_line_id, order_id)))
        return bank_statement_line_list

    def create_bank_statement(self):
        self.ensure_one()
        mk_instance_id = self.mk_instance_id
        bank_statement_obj = self.env['account.bank.statement']
        statement_id = bank_statement_obj.search([('shopify_ref', '=', self.report_id)], limit=1)
        if statement_id:
            statement_id.write({'shopify_payout_id': self.id, 'line_ids': self.prepare_bank_statement_line(statement_id=statement_id)})
            return statement_id
        name = '{} [{}] [{}]'.format(mk_instance_id.name, self.payout_date, self.report_id)
        statement_line_list = self.prepare_bank_statement_line()
        vals = {'name': name,
                'shopify_ref': self.report_id,
                'shopify_payout_id': self.id,
                'journal_id': mk_instance_id.payout_journal_id.id,
                'date': self.payout_date,
                'currency_id': self.currency_id.id,
                'line_ids': statement_line_list,
                'balance_start': 0.0,
                'balance_end_real': 0.0}
        statement_id = bank_statement_obj.create(vals)
        return statement_id

    def prepare_payout_line_dict(self, transaction_dict, transaction_currency_id, mk_instance_id):
        order_id = self.env['sale.order']
        if transaction_dict.get('source_order_id'):
            order_id = self.env['sale.order'].search([('mk_id', '=', transaction_dict.get('source_order_id')), ('mk_instance_id', '=', mk_instance_id.id)], limit=1)
        transaction_label = "{}".format(order_id.name and '{}-{}'.format(order_id.name, transaction_dict.get('id')) or '{}-{}'.format(transaction_dict.get('type'), transaction_dict.get('id') or self.report_id))
        # if transaction_dict.get('type') == 'refund':
        #     transaction_label = "{}-{}".format('Refund', transaction_label)
        return {
            'transaction_id': transaction_dict.get('id'),
            'transaction_type': transaction_dict.get('type'),
            'currency_id': transaction_currency_id.id,
            'amount': transaction_dict.get('amount'),
            'fee': transaction_dict.get('fee'),
            'net_amount': transaction_dict.get('net'),
            'source_order_id': transaction_dict.get('source_order_id'),
            'source_type': transaction_dict.get('source_type'),
            'processed_at': convert_shopify_datetime_to_utc(transaction_dict.get('processed_at')),
            'order_id': order_id.id or False,
            'transaction_label': transaction_label,
        }

    def prepare_fee_line_dict(self, payout_dict, payout_currency_id):
        fees_amount = float(payout_dict.get('summary').get('charges_fee_amount', 0.0)) + float(payout_dict.get('summary').get('refunds_fee_amount', 0.0)) + float(
            payout_dict.get('summary').get('adjustments_fee_amount', 0.0))
        if not fees_amount:
            return False
        transaction_label = 'fees-{}'.format(payout_dict.get('id'))
        return {
            'transaction_type': 'fees',
            'currency_id': payout_currency_id.id,
            'amount': -fees_amount,
            'fee': 0.0,
            'net_amount': fees_amount,
            'transaction_label': transaction_label,
        }

    def shopify_import_payout_report(self, mk_instance_id, from_date=False, to_date=False):
        currency_obj = self.env['res.currency']
        if not mk_instance_id.payout_journal_id:
            raise UserError(_("Please define Payout Journal on Instance >> Payout >> Payout Journal."))
        payout_list, start_date, end_date = self.fetch_payout_from_shopify(mk_instance_id, from_date, to_date)
        for payout in payout_list:
            payout_dict = payout.to_dict()
            payout_id = payout_dict.get('id')
            payout_currency_id = currency_obj.search([('name', '=', payout_dict.get('currency'))], limit=1)
            if not payout_currency_id:
                break
            existing_payout_id = self.search([('report_id', '=', payout_id), ('mk_instance_id', '=', mk_instance_id.id)])
            if existing_payout_id:
                continue
            payout_vals = {'report_id': payout_id,
                           'currency_id': payout_currency_id.id,
                           'payout_date': convert_shopify_datetime_to_utc(payout_dict.get('date')),
                           'amount': payout_dict.get('amount'),
                           'mk_instance_id': mk_instance_id.id}
            transaction_list = self.fetch_transaction_of_payout(payout_id)
            transaction_vals_list = []
            for transaction in transaction_list:
                transaction_dict = transaction.to_dict()
                transaction_currency_id = currency_obj.search([('name', '=', transaction_dict.get('currency'))], limit=1)
                transaction_vals_list.append((0, 0, self.prepare_payout_line_dict(transaction_dict, transaction_currency_id, mk_instance_id)))
            fees_line_vals = self.prepare_fee_line_dict(payout_dict, payout_currency_id)
            if fees_line_vals:
                transaction_vals_list.append((0, 0, fees_line_vals))
            payout_vals['payout_line_ids'] = transaction_vals_list
            payout_id = self.create(payout_vals)
            statement_id = payout_id.create_bank_statement()
            payout_id.bank_statement_id = statement_id.id
            if mk_instance_id.is_payout_auto_process:
                payout_id.button_reconcile()
            self._cr.commit()
        if not to_date:
            mk_instance_id.payout_report_last_sync_date = end_date
        self._cr.commit()
        return True

    def cron_auto_import_shopify_payout_report(self, mk_instance_id):
        try:
            cr = registry(self._cr.dbname).cursor()
            self = self.with_env(self.env(cr=cr))
            mk_instance_id = self.env['mk.instance'].browse(mk_instance_id)
            if mk_instance_id.state == 'confirmed':
                self.shopify_import_payout_report(mk_instance_id)
                _logger.info("import shopify payout process is finished and committed")
        except Exception:
            _logger.error("Error during import shopify payout report", exc_info=True)
            raise
        finally:
            try:
                self._cr.close()
            except Exception:
                pass
        return True

    def shopify_process_payout_report(self, mk_instance_id):
        mk_instance_id = self.env['mk.instance'].sudo().browse(mk_instance_id)
        payout_ids = self.search([('mk_instance_id', '=', mk_instance_id.id), ('report_id', '!=', False), ('state', 'in', ['draft', 'posted', 'confirm'])])
        for payout_id in payout_ids:
            if payout_id.bank_statement_id.state != 'open':
                return True
            payout_id.reconcile_transactions(payout_id.bank_statement_id)
        return True

    def _convert_amount_currency(self, statement_line_id, aml_id):
        amount_currency = 0.0
        statement_currency = statement_line_id.currency_id or statement_line_id.statement_id.currency_id
        statement_company = statement_line_id.statement_id.company_id
        if aml_id.company_id.currency_id.id != statement_currency.id:
            amount_currency = aml_id.currency_id._convert(aml_id.amount_currency, statement_currency, statement_company, statement_line_id.date)
        elif aml_id.move_id.currency_id.id != statement_currency.id:
            amount_currency = aml_id.move_id.currency_id._convert(aml_id.balance, statement_currency, statement_company, statement_line_id.date)
        currency = aml_id.currency_id or aml_id.move_id.currency_id
        return currency, amount_currency

    def reconcile_invoices(self, statement_line_id, invoice_ids):
        paid_invoices = invoice_ids.filtered(lambda x: x.payment_state in ['paid', 'in_payment'])
        unpaid_invoices = invoice_ids.filtered(lambda x: x.payment_state == 'not_paid')
        reconciled_move_lines = self.env['account.move.line']
        if paid_invoices:
            for invoice in paid_invoices:
                reconciled_payments = invoice._get_reconciled_payments()
                reconciled_move_lines |= reconciled_payments.invoice_line_ids.filtered(lambda x: getattr(x, 'debit' if invoice.move_type == 'out_invoice' else 'credit', None) != 0.0)
        total_amount = 0.0
        currency_ids = set([])
        move_line_data_for_reconcile = []
        for u_line in unpaid_invoices.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable' and not l.reconciled):
            amount = u_line.balance
            if not u_line.amount_currency:
                currency, amount_currency = self._convert_amount_currency(statement_line_id, u_line)
                currency_ids.add(currency)
                if amount_currency:
                    amount = amount_currency
            total_amount += amount
            move_line_data_for_reconcile.append({
                'name': u_line.move_id.name,
                'id': u_line.id,
                'balance': -amount,
                'currency_id': u_line.currency_id.id,
            })

        for r_line in reconciled_move_lines:
            amount = r_line.balance
            if not r_line.amount_currency:
                currency, amount_currency = self._convert_amount_currency(statement_line_id, r_line)
                currency_ids.add(currency)
                if amount_currency:
                    amount = amount_currency
            total_amount += amount

        currency_ids = list(currency_ids)
        if round(statement_line_id.amount, 10) == round(total_amount, 10) and (
                not statement_line_id.currency_id or statement_line_id.currency_id.id == self.bank_statement_id.currency_id.id):
            if len(currency_ids) == 1 and not statement_line_id.currency_id:
                if currency_ids != statement_line_id.statement_id.currency_id:
                    statement_line_id.write({'currency_id': currency_ids.id})
            try:
                for rm_line in reconciled_move_lines:
                    move_line_data_for_reconcile.append({'id': rm_line.id})
                if move_line_data_for_reconcile:
                    statement_line_id.reconcile(lines_vals_list=move_line_data_for_reconcile)
            except Exception as e:
                statement_line_id.shopify_payout_line_id.write({'error_message': 'A error encountered while reconciling statement line : %s ' % e})
                statement_line_id.button_undo_reconciliation()

        if statement_line_id.is_reconciled:
            statement_line_id.shopify_payout_line_id.write({'error_message': False, 'warn_message': False})
        return True

    def reconcile_transactions(self):
        statement_id = self.bank_statement_id
        if statement_id.state == 'open':
            statement_id.button_post()
        for line_id in statement_id.line_ids.filtered(lambda x: not x.is_reconciled and x.shopify_payout_line_id):
            payout_line_id = line_id.shopify_payout_line_id
            if payout_line_id.transaction_type in ["charge", "refund"]:
                invoice_ids = payout_line_id.order_id.invoice_ids.filtered(
                    lambda x: x.state == 'posted' and x.move_type == INVOICE_AND_PAYMENT_TYPES[payout_line_id.transaction_type]['invoice_type'])
                if not invoice_ids:
                    continue
                self.reconcile_invoices(line_id, invoice_ids)
            else:
                payout_account_config_id = self.mk_instance_id.payout_account_config_ids.filtered(lambda x: x.transaction_type == payout_line_id.transaction_type)
                if not payout_account_config_id:
                    continue
                line_id.reconcile(lines_vals_list=[{'name': line_id.payment_ref, 'balance': -line_id.amount, 'account_id': payout_account_config_id.account_id.id, 'currency_id': line_id.currency_id.id}])
            self._cr.commit()
        return True

    def button_reconcile(self):
        self.ensure_one()
        if self.state == 'draft':
            self.button_post()
        self.reconcile_transactions()
        if all([p_line.is_reconciled for p_line in self.payout_line_ids]):
            self.button_validate()
        return True

    def button_manual_reconcile(self):
        if hasattr(self.bank_statement_id, 'action_bank_reconcile_bank_statements'):
            return getattr(self.bank_statement_id, 'action_bank_reconcile_bank_statements')()
        raise UserError(_("Reconciliation function not found to do manual reconciliation! Try auto reconciliation instead."))

    def button_post(self):
        for payout in self:
            if not payout.bank_statement_id:
                payout.bank_statement_id = self.create_bank_statement()
            payout.bank_statement_id.write({'line_ids': payout.prepare_bank_statement_line(statement_id=payout.bank_statement_id)})
            payout.bank_statement_id.button_post()

    def button_validate(self):
        self.bank_statement_id.button_validate_or_action()

    def button_reprocess(self):
        self.bank_statement_id.button_reprocess()

    def button_reopen(self):
        self.bank_statement_id.button_reopen()

    # def generate_bank_statement(self):
    #     self.write({'bank_statement_id': self.create_bank_statement()})
    #     return True

    def unlink(self):
        for payout in self:
            if payout.state != 'draft':
                raise UserError(_('You cannot delete a processing or validated payout.'))
        return super(ShopifyPayout, self).unlink()


class ShopifyPayoutLine(models.Model):
    _name = "shopify.payout.line"
    _description = "Shopify Payout Line"

    @api.depends('payout_id.bank_statement_id', 'payout_id.bank_statement_id.line_ids')
    def _compute_bank_statement_line(self):
        for record in self:
            record.bank_statement_line_id = record.payout_id.bank_statement_id.line_ids.filtered(lambda x: x.shopify_payout_line_id == record)

    @api.depends('source_order_id')
    def _compute_order_id(self):
        for record in self:
            record.order_id = self.env['sale.order'].search([('mk_id', '=', record.source_order_id), ('mk_instance_id', '=', record.payout_id.mk_instance_id.id)], limit=1)
            if record.order_id:
                record.warn_message = False

    payout_id = fields.Many2one("shopify.payout", "Payout", ondelete='cascade')
    transaction_id = fields.Char("Transaction ID")
    transaction_type = fields.Selection(PAYOUT_TRANSACTION_TYPE, help="The type of the balance transaction", string="Transaction Type")
    currency_id = fields.Many2one('res.currency', string="Currency")
    amount = fields.Float("Amount")
    fee = fields.Float("Fees")
    net_amount = fields.Float("Net Amount")
    source_order_id = fields.Char("Source Order ID", help="The id of the Order that this transaction ultimately originated from.")
    source_type = fields.Char("Source Type", help="The type of the resource leading to the transaction.")
    processed_at = fields.Datetime("Processed Date", help="The time the transaction was processed.")
    order_id = fields.Many2one("sale.order", string="Order Reference", compute="_compute_order_id")
    bank_statement_line_id = fields.Many2one("account.bank.statement.line", compute="_compute_bank_statement_line", store=True, string="Bank Statement Line")
    transaction_label = fields.Char(string="Label", help="Technical field that will use on label field while creating bank statement line.")

    # == Display purpose fields ==
    is_reconciled = fields.Boolean(string='Is Reconciled', related="bank_statement_line_id.is_reconciled")
    warn_message = fields.Text(string="Warning Message", copy=False)
    error_message = fields.Text(string="Error Message", copy=False)

    def button_undo_reconciliation(self):
        self.ensure_one()
        self.bank_statement_line_id.button_undo_reconciliation()
