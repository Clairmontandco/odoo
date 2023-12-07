import json
import babel
import random
import base64
from lxml import etree
from odoo.osv import expression
from datetime import date, timedelta
from odoo import models, fields, api, _
from odoo.tools import date_utils, float_round
from dateutil.relativedelta import relativedelta
from odoo.tools.misc import format_date, get_lang
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo.exceptions import UserError, ValidationError
from babel.dates import format_date as babel_format_date
from babel.dates import get_quarter_names, format_datetime


class MkInstance(models.Model):
    _name = "mk.instance"
    _order = 'sequence, name'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Marketplace Instance'

    filter_date = {'date_from': '', 'date_to': '', 'filter': 'this_month'}

    def _get_kanban_graph(self):
        self.dashboard_graph = json.dumps(self.get_bar_graph_datas())

    def _get_mk_kanban_badge_color(self):
        default_code = "#7C7BAD"
        # Hook type method that will get default kanban badge color according to marketplace type.
        if hasattr(self, '%s_mk_kanban_badge_color' % self.marketplace):
            default_code = getattr(self, '%s_mk_kanban_badge_color' % self.marketplace)
        return default_code

    @api.onchange('marketplace')
    def _get_mk_default_api_limit(self):
        api_limit = 250
        # Hook type method that will get default api limit according to marketplace type.
        if hasattr(self, '%s_mk_default_api_limit' % self.marketplace):
            api_limit = getattr(self, '%s_mk_default_api_limit' % self.marketplace)()
        self.api_limit = api_limit

    def _get_mk_kanban_counts(self):
        for mk_instance_id in self:
            mk_instance_id.mk_listing_count = len(mk_instance_id.mk_listing_ids)
            mk_instance_id.mk_order_count = self.env['sale.order'].search_count([('mk_instance_id', '=', mk_instance_id.id)])
            mk_instance_id.mk_queue_count = len(mk_instance_id.mk_queue_ids.filtered(lambda x: x.state != 'processed'))

    def _kanban_dashboard_graph(self):
        for mk_instance_id in self:
            chart_data = mk_instance_id.get_bar_graph_datas()
            mk_instance_id.kanban_dashboard_graph = json.dumps(chart_data)
            mk_instance_id.is_sample_data = chart_data[0].get('is_sample_data', False)

    def _get_discount_product(self):
        # Hook type method that will get default discount according to marketplace type.
        discount_product = False
        if hasattr(self, '_get_%s_discount_product' % self.marketplace):
            discount_product = getattr(self, '_get_%s_discount_product' % self.marketplace)
        return discount_product

    def _get_delivery_product(self):
        # Hook type method that will get default discount according to marketplace type.
        delivery_product = False
        if hasattr(self, '_get_%s_delivery_product' % self.marketplace):
            delivery_product = getattr(self, '_get_%s_delivery_product' % self.marketplace)
        return delivery_product

    def _get_default_warehouse(self):
        company_id = self.company_id if self.company_id else self.env.company
        warehouse_id = self.env['stock.warehouse'].search([('company_id', '=', company_id.id)], limit=1)
        return warehouse_id.id if warehouse_id else False

    @api.model
    def _lang_get(self):
        return self.env['res.lang'].get_installed()

    # TODO: Is environment needed?
    name = fields.Char(string='Name', required=True, help="Name of your marketplace instance.")
    color = fields.Integer('Color Index')
    sequence = fields.Integer(default=1, help="The sequence field is used to define Instance Sequence.")
    marketplace = fields.Selection(selection=[], string='Marketplace', default='')
    state = fields.Selection(selection=[('draft', 'Draft'), ('confirmed', 'Confirmed'), ('error', 'Error')], default='draft')
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)
    country_id = fields.Many2one('res.country', string='Country', default=lambda self: self.env.company.country_id)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True, default=_get_default_warehouse)
    api_limit = fields.Integer("API Record Count", help="Record limit while perform api calling.")
    kanban_badge_color = fields.Char(default=_get_mk_kanban_badge_color)
    log_level = fields.Selection([('all', 'All'), ('success', 'Success'), ('error', 'Error')], string="Log Level", default="error")
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string="Company Currency")
    show_in_systray = fields.Boolean("Show in Systray Menu?", copy=False)
    queue_batch_limit = fields.Integer("Queue Batch Limit", default=100, help="Odoo will create a batch with defined limit.")
    image = fields.Binary("Marketplace Image", attachment=True, help="This field holds the image used as photo for the marketplace, limited to 1024x1024px.")
    image_medium = fields.Binary("Medium-sized photo", related="image", store=True,
                                 help="Medium-sized photo of the marketplace. It is automatically resized as a 128x128px image, with aspect ratio preserved. ")
    image_small = fields.Binary("Small-sized photo", related="image", store=True,
                                help="Small-sized photo of the marketplace. It is automatically resized as a 64x64px image, with aspect ratio preserved. ")
    lang = fields.Selection(_lang_get, string='Language', default=lambda self: self.env.lang, help="Instance language.")

    # Product Fields
    is_create_products = fields.Boolean("Create Odoo Products?", help="If Odoo products not found while Sync create Odoo products.")
    is_update_odoo_product_category = fields.Boolean("Update Category in Odoo Products?", help="Update Odoo Products Category.")
    is_export_product_sale_price = fields.Boolean("Export Odoo Product's Sale Price?", help="Directly exporting the product's sale price instead of the price from the pricelist")
    is_sync_images = fields.Boolean("Sync Listing Images?", help="If true then Images will be sync at the time of Import Listing.")
    sync_product_with = fields.Selection([('barcode', 'Barcode'), ('sku', 'SKU'), ('barcode_or_sku', 'Barcode or SKU')], string="Sync Product With", default="barcode_or_sku")
    last_listing_import_date = fields.Datetime("Last Listing Imported On", copy=False)
    last_listing_price_update_date = fields.Datetime("Last Listing Price Updated On", copy=False)

    # Stock Fields
    stock_field_id = fields.Many2one('ir.model.fields', string='Stock Based On', help="At the time of Export/Update inventory this field is used.",
                                     default=lambda self: self.env['ir.model.fields'].search([('model_id.model', '=', 'product.product'), ('name', '=', 'qty_available')]))
    last_stock_update_date = fields.Datetime("Last Stock Exported On", copy=False, help="Date were stock updated to marketplace.")
    last_stock_import_date = fields.Datetime("Last Stock Imported On", copy=False, help="Date were stock imported from marketplace.")
    is_validate_adjustment = fields.Boolean("Validate Inventory Adjustment?", help="If true then validate Inventory adjustment at the time of Import Stock Operation.")

    # Order Fields
    use_marketplace_sequence = fields.Boolean("Use Marketplace Order Sequence?", default=True)
    order_prefix = fields.Char(string='Order Prefix', help="Order name will be set with given Prefix while importing Order.")
    fbm_order_prefix = fields.Char(string='Order Prefix (Fulfilment by Marketplace)', help="Order name will be set with given Prefix while importing fulfillment by marketplace orders.")
    team_id = fields.Many2one('crm.team', string='Sales Team', default=lambda self: self.env['crm.team'].search([], limit=1), help='Sales Team used for imported order.')
    discount_product_id = fields.Many2one('product.product', string='Discount Product', domain=[('type', '=', 'service')],
                                          help='Discount product used in sale order line.')
    delivery_product_id = fields.Many2one('product.product', string='Delivery Product', domain=[('type', '=', 'service')], help="""Delivery product used in sale order line.""")
    last_order_sync_date = fields.Datetime("Last Order Imported On", copy=False)
    import_order_after_date = fields.Datetime("Import Order After", copy=False)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', domain="[('company_id', '=', company_id)]", check_company=True)
    tax_system = fields.Selection([('default', "Odoo's Default Tax Behaviour (Taxes will be taken from Odoo Product)"), ('according_to_marketplace', 'Follow Marketplace Tax (Create a new tax if not found)')], default='according_to_marketplace',
                                  help="""1. Odoo's Default Tax Behaviour - Tax will be applied based on Odoo's tax and fiscal position configuration,\n2. Create a new Tax if not found - System will create a new taxes according to the marketplace tax rate if not found in the Odoo.""")
    tax_account_id = fields.Many2one('account.account', string='Tax Account', check_company=True, help="Account that will be set while creating tax.")
    tax_refund_account_id = fields.Many2one('account.account', string='Tax Account on Credit Notes', check_company=True, help="Account that will be set while creating tax.")
    salesperson_user_id = fields.Many2one('res.users', string='Salesperson', domain="[('share', '=', False)]", help="Selected sales person will be used to process order.")
    use_marketplace_currency = fields.Boolean("Use Marketplace Order Currency?", default=True,
                                              help="If it's true, the order will be imported with the currency that is available in the marketplace. Otherwise, it will use the company's currency.")
    analytic_account_id = fields.Many2one('account.analytic.account', 'Analytic Account', help="Set the Analytic account for Marketplace orders"
                                                                                                              "\n- The configured analytic account for this instance will be assigned to all sales orders created by the connector. This means that the Analytic Default Rule set up in Odoo will not be applied to Marketplace orders."
                                                                                                              "\n- However, if you prefer to use the Odoo Analytic Default Rule, you do not need to configure any analytic account here.")

    # Customer Fields
    account_receivable_id = fields.Many2one('account.account', string='Receivable Account',
                                            domain="[('deprecated', '=', False), ('internal_type', '=', 'receivable'), ('company_id', '=', company_id)]",
                                            help="While creating Customer set this field in Account Receivable instead of default.")
    account_payable_id = fields.Many2one('account.account', string='Payable Account',
                                         domain="[('deprecated', '=', False), ('internal_type', '=', 'payable'), ('company_id', '=', company_id)]",
                                         help="While creating Customer set this field in Account Payable instead of default.")
    last_customer_import_date = fields.Datetime("Last Customers Imported On", copy=False)

    # Scheduled actions
    cron_ids = fields.One2many("ir.cron", "mk_instance_id", "Automated Actions", context={'active_test': False}, groups="base.group_system")

    # Emails & Notifications
    notification_ids = fields.One2many("mk.notification", "mk_instance_id", "Marketplace Notification")

    # Dashboard Fields
    mk_listing_ids = fields.One2many('mk.listing', 'mk_instance_id', string="Listing")
    mk_listing_count = fields.Integer("Listing Count", compute='_get_mk_kanban_counts')
    mk_order_ids = fields.One2many('sale.order', 'mk_instance_id', string="Orders")
    mk_order_count = fields.Integer("Order Count", compute='_get_mk_kanban_counts')
    mk_invoice_ids = fields.One2many('account.move', 'mk_instance_id', string="Invoices")
    mk_invoice_count = fields.Integer("Invoice Count", compute='_get_mk_kanban_counts')
    mk_total_revenue = fields.Float("Revenue", compute='_get_mk_kanban_counts')
    mk_shipment_ids = fields.One2many('stock.picking', 'mk_instance_id', string="Shipments")
    mk_shipment_count = fields.Integer("Shipment Count", compute='_get_mk_kanban_counts')
    mk_queue_ids = fields.One2many('mk.queue.job', 'mk_instance_id', string="Queue Job")
    mk_queue_count = fields.Integer("Queue Count", compute='_get_mk_kanban_counts')
    mk_customer_ids = fields.Many2many("res.partner", "mk_instance_res_partner_rel", "partner_id", "marketplace_id", string="Customers")

    mk_customer_count = fields.Integer("Customer Count", compute='_get_mk_kanban_counts')

    mk_log_ids = fields.One2many('mk.log', 'mk_instance_id', string="Logs")

    # Kanban bar graph
    kanban_dashboard_graph = fields.Text(compute='_kanban_dashboard_graph')

    # Activity
    mk_activity_type_id = fields.Many2one('mail.activity.type', string='Activity', domain="[('res_model', '=', False)]")
    activity_date_deadline_range = fields.Integer(string='Due Date In')
    activity_date_deadline_range_type = fields.Selection([('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months'), ], string='Due type', default='days')
    activity_user_ids = fields.Many2many('res.users', string='Responsible')

    is_sample_data = fields.Boolean("Is Sample Data", compute='_kanban_dashboard_graph')

    tax_rounding = fields.Integer(string="Tax Rounding", default=2)

    def get_all_marketplace(self):
        # marketplace_list = self.search([]).mapped('marketplace')
        marketplace_list = [marketplace[0] for marketplace in self.env['mk.instance'].fields_get()['marketplace']['selection'] if marketplace]
        return marketplace_list and marketplace_list or []

    @api.onchange('marketplace')
    def _onchange_marketplace(self):
        default_code, image = "#7C7BAD", False
        # Hook type method that will get default kanban badge color according to marketplace type.
        if hasattr(self, '%s_mk_kanban_badge_color' % self.marketplace):
            default_code = getattr(self, '%s_mk_kanban_badge_color' % self.marketplace)()
        self.kanban_badge_color = default_code
        if hasattr(self, '%s_mk_kanban_image' % self.marketplace):
            image_path = getattr(self, '%s_mk_kanban_image' % self.marketplace)()
            image = base64.b64encode(open(image_path, 'rb').read())
        if not self.delivery_product_id and hasattr(self, '_get_%s_delivery_product' % self.marketplace):
            self.delivery_product_id = getattr(self, '_get_%s_delivery_product' % self.marketplace)()
        if not self.discount_product_id and hasattr(self, '_get_%s_discount_product' % self.marketplace):
            self.discount_product_id = getattr(self, '_get_%s_discount_product' % self.marketplace)()
        self.image = image

    def _update_default_products_in_instance(self):
        if not self.delivery_product_id and hasattr(self, '_get_%s_delivery_product' % self.marketplace):
            self.delivery_product_id = getattr(self, '_get_%s_delivery_product' % self.marketplace)()
        if not self.discount_product_id and hasattr(self, '_get_%s_discount_product' % self.marketplace):
            self.discount_product_id = getattr(self, '_get_%s_discount_product' % self.marketplace)()

    @api.model
    def create(self, vals):
        res = super(MkInstance, self).create(vals)
        self.env['ir.cron'].setup_schedule_actions(res)
        res._update_default_products_in_instance()
        return res

    def write(self, vals):
        res = super(MkInstance, self).write(vals)
        for instance in self:
            instance._update_default_products_in_instance()
        return res

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "[{}] {}".format(dict(record._fields['marketplace'].selection).get(record.marketplace), record.name or '')))
        return result

    def action_confirm(self):
        self.ensure_one()
        if hasattr(self, '%s_action_confirm' % self.marketplace):
            getattr(self, '%s_action_confirm' % self.marketplace)()
        self.write({'state': 'confirmed'})
        return True

    def reset_to_draft(self):
        self.write({'state': 'draft'})

    def get_marketplace_operation_wizard(self):
        if hasattr(self, '%s_marketplace_operation_wizard' % self.marketplace):
            return getattr(self, '%s_marketplace_operation_wizard' % self.marketplace)()
        else:
            raise UserError(_("Something went wrong! Please contact your integration provider."))

    def get_marketplace_import_operation_wizard(self):
        if hasattr(self, '%s_marketplace_import_operation_wizard' % self.marketplace):
            return getattr(self, '%s_marketplace_import_operation_wizard' % self.marketplace)()
        else:
            return self.env.ref('base_marketplace.action_marketplace_import_operation').sudo().read()[0]

    def get_marketplace_export_operation_wizard(self):
        if hasattr(self, '%s_marketplace_export_operation_wizard' % self.marketplace):
            return getattr(self, '%s_marketplace_export_operation_wizard' % self.marketplace)()
        else:
            return self.env.ref('base_marketplace.action_marketplace_export_operation').sudo().read()[0]

    def is_order_create_notification_message(self, count, marketplace):
        # Dynamic method for get notification title and message
        title = _('{marketplace} Orders Import'.format(marketplace=marketplace))
        message = {'error': '{count} {marketplace} order(s) facing issue for {instance} Instance'.format(count=count, marketplace=marketplace, instance=self.name), 'success': _(
            '{count} {marketplace} order(s) imported successfully for {instance} Instance.'.format(count=count, marketplace=marketplace, instance=self.name))}
        return title, message

    def is_product_import_notification_message(self, count, marketplace):
        # Dynamic method for get notification title and message
        title = _('{marketplace} Product Import'.format(marketplace=marketplace))
        message = {'error': '{count} {marketplace} product(s) facing issue for {instance} Instance'.format(count=count, marketplace=marketplace, instance=self.name),
                   'success': _('{count} {marketplace} product(s) imported successfully for {instance} Instance.'.format(count=count, marketplace=marketplace, instance=self.name))}
        return title, message

    def get_smart_notification_message(self, notify_field, count, marketplace):
        # Hook type method that will get notification title and message according to `notify_field`
        title, message = 'No Title', 'Nothing to display'
        if hasattr(self, '%s_notification_message' % notify_field):
            title, message = getattr(self, '%s_notification_message' % notify_field)(count, marketplace)
        return title, message

    def send_smart_notification(self, notify_field, notify_type, count):
        """ Method to send Smart Notification to Users that is configured in Marketplace Notification Tab.
        :param notify_field: order_create, product_create
        :param notify_type: success, error, all.
        :param count: count
        :return: True
        exp. : self.send_smart_notification('is_order_create', 'success', 5)
        """
        notification_ids = self.notification_ids
        for notification_id in notification_ids:
            if hasattr(notification_id, notify_field) and count > 0:
                notify = getattr(notification_id, notify_field)
                if notify_type == 'error' and notification_id.type not in ['error', 'all']:
                    continue
                if notify_type == 'success' and notification_id.type not in ['success', 'all']:
                    continue
                if notify:
                    marketplace = notification_id.mk_instance_id.marketplace
                    marketplace_name = dict(self._fields['marketplace'].selection).get(marketplace) or ''
                    title, message = self.get_smart_notification_message(notify_field, count, marketplace_name)
                    if title and message:
                        warning = False if notify_type == 'success' else True
                        message = message.get('success') if notify_type == 'success' else message.get('error')
                        self.env['bus.bus']._sendone(notification_id.user_id.partner_id, 'simple_notification',
                                                     {'title': title, 'message': message, 'sticky': notification_id.is_sticky, 'warning': warning})

    def action_create_queue(self, type):
        self.ensure_one()
        queue_obj = self.env['mk.queue.job']

        queue_id = queue_obj.create({'type': type,
                                     'mk_instance_id': self.id,
                                     'update_existing_product': self.env.context.get('update_existing_product'),
                                     'update_product_price': self.env.context.get('update_product_price')})
        if self.env.context.get('active_model', '') == 'mk.instance':
            message = '{} Queue {} created successfully.'.format(type.title(), queue_id.name)
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {'title': 'Queue Created', 'message': message, 'sticky': False, 'warning': False})
        return queue_id

    def _graph_title_and_key(self):
        return ['Untaxed Total', _('Untaxed Total')]

    def _get_bar_graph_select_query(self):
        """
        Returns a tuple containing the base SELECT SQL query used to gather
        the bar graph's data as its first element, and the arguments dictionary
        for it as its second.
        """
        return ('''
            SELECT SUM(amount_untaxed) AS total, MIN(date_order) AS aggr_date
            FROM sale_order
            WHERE mk_instance_id = %(mk_instance_id)s
            AND state not in ('cancel')''', {'mk_instance_id': self.id})

    def get_bar_graph_datas(self):
        data = []
        today = fields.Datetime.now(self)
        # data.append({'label': _('Past'), 'value': 0.0, 'type': 'past'})
        day_of_week = int(format_datetime(today, 'e', locale=self._context.get('lang') or 'en_US'))
        first_day_of_week = today + timedelta(days=-day_of_week + 1)
        for i in range(-5, 1):
            if i == 0:
                label = _('This Week')
            else:
                start_week = first_day_of_week + timedelta(days=i * 7)
                end_week = start_week + timedelta(days=6)
                if start_week.month == end_week.month:
                    label = str(start_week.day) + '-' + str(end_week.day) + ' ' + babel_format_date(end_week, 'MMM', locale=get_lang(self.env).code)
                else:
                    label = babel_format_date(start_week, 'd MMM', locale=get_lang(self.env).code) + '-' + babel_format_date(end_week, 'd MMM', locale=get_lang(self.env).code)
            data.append({'label': label, 'value': 0.0, 'type': 'past' if i < 0 else 'future'})

        # Build SQL query to find amount aggregated by week
        (select_sql_clause, query_args) = self._get_bar_graph_select_query()
        query = ''
        o_start_date = today + timedelta(days=-day_of_week + 1)
        start_date = today + timedelta(days=-day_of_week + 1)
        for i in range(-5, 1):
            if i == -5:
                start_date = o_start_date + timedelta(days=i * 7)
                next_date = start_date + timedelta(days=7)
                query += "(" + select_sql_clause + " and date_order >= '" + start_date.strftime(DEFAULT_SERVER_DATE_FORMAT) + "' and date_order < '" + next_date.strftime(DEFAULT_SERVER_DATE_FORMAT) + "')"
            else:
                next_date = start_date + timedelta(days=7)
                query += " UNION ALL (" + select_sql_clause + " and date_order >= '" + start_date.strftime(DEFAULT_SERVER_DATE_FORMAT) + "' and date_order < '" + next_date.strftime(DEFAULT_SERVER_DATE_FORMAT) + "')"
            start_date = next_date
        self.env.cr.execute(query, query_args)
        query_results = self.env.cr.dictfetchall()

        for index in range(0, len(query_results)):
            if query_results[index].get('aggr_date') != None:
                data[index]['value'] = query_results[index].get('total')

        # Added random Sample data for better visualization.
        is_sample_data = True
        for index in range(0, len(query_results)):
            if query_results[index].get('total') not in [None, 0.0]:
                is_sample_data = False
                data[index]['value'] = query_results[index].get('total')

        [graph_title, graph_key] = self._graph_title_and_key()

        if is_sample_data:
            for index in range(0, len(query_results)):
                data[index]['type'] = 'o_sample_data'
                # we use unrealistic values for the sample data
                data[index]['value'] = random.randint(0, 20)
                graph_key = _('Sample data')

        return [{'values': data, 'title': graph_title, 'key': graph_key, 'is_sample_data': is_sample_data}]

    def _format_currency_amount(self, amount, currency_id):
        currency_id = self.env['res.currency'].browse(currency_id)
        pre = post = u''
        if currency_id.position == 'before':
            pre = u'{symbol}\N{NO-BREAK SPACE}'.format(symbol=currency_id.symbol or '')
        else:
            post = u'\N{NO-BREAK SPACE}{symbol}'.format(symbol=currency_id.symbol or '')
        return u'{pre}{0}{post}'.format(amount, pre=pre, post=post)

    @api.model
    def systray_get_marketplaces(self):
        mk_instance_ids = []
        if self.env.user.has_group('base_marketplace.group_base_marketplace'):
            mk_instance_ids = self.env['mk.instance'].search_read([('show_in_systray', '=', True), ('state', '=', 'confirmed')],
                                                                  ['id', 'name', 'marketplace', 'image_medium', 'mk_order_count', 'mk_listing_count', 'mk_total_revenue',
                                                                   'company_currency_id'])
        user_activities = {}
        for mk_instance_dict in mk_instance_ids:
            user_activities[mk_instance_dict['id']] = {'id': mk_instance_dict['id'],
                                                       'name': mk_instance_dict['name'],
                                                       'model': 'mk.instance',
                                                       'type': mk_instance_dict['marketplace'],
                                                       'icon': mk_instance_dict['image_medium'],
                                                       'mk_order_count': mk_instance_dict['mk_order_count'],
                                                       'mk_listing_count': mk_instance_dict['mk_listing_count'],
                                                       'mk_total_revenue': self._format_currency_amount(mk_instance_dict['mk_total_revenue'],
                                                                                                        mk_instance_dict['company_currency_id'][0])}
        return list(user_activities.values())

    def action_marketplace_open_instance_view(self):
        form_id = self.sudo().env.ref('base_marketplace.marketplace_instance_form_view')
        action = {
            'name': _('Marketplace Instance'),
            'view_id': False,
            'res_model': 'mk.instance',
            'context': self._context,
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(form_id.id, 'form')],
            'type': 'ir.actions.act_window',
        }
        return action

    def redirect_to_general_dashboard(self):
        if self.env.user.has_group('base_marketplace.group_base_marketplace_manager'):
            return self.sudo().env.ref('base_marketplace.backend_mk_general_dashboard').read()[0]
        return self.sudo().env.ref('base_marketplace.action_marketplace_dashboard').read()[0]

    def redirect_to_sales_report(self):
        action = self.env['sale.report'].redirect_to_mk_sale_report()
        action['display_name'] = _("{} Sales Analysis".format(self.name))
        action['domain'] = [('mk_instance_id', '=', self.id)]
        return action

    def _get_margin_value(self, value, previous_value=0.0):
        margin = 0.0
        if (value != previous_value) and (value != 0.0 and previous_value != 0.0):
            margin = float_round((float(value-previous_value) / previous_value or 1) * 100, precision_digits=2)
        return margin

    def _get_top_10_performing_products(self, dashboard_data_list, sales_domain):
        report_product_lines = self.env['sale.report'].read_group(domain=sales_domain + [('product_type', '!=', 'service')],
            fields=['product_tmpl_id', 'product_uom_qty', 'price_total'],
            groupby='product_tmpl_id', orderby='price_total desc', limit=10)

        for product_line in report_product_lines:
            product_tmpl_id = self.env['product.template'].browse(product_line['product_tmpl_id'][0])
            dashboard_data_list['best_sellers'].append({'id': product_tmpl_id.id,
                                                        'name': product_tmpl_id.name,
                                                        'qty': product_line['product_uom_qty'],
                                                        'sales': product_line['price_total']})
        return dashboard_data_list

    def _get_top_10_customers(self, total_orders, dashboard_data_list, sales_domain):
        report_customer_lines = self.env['sale.report'].read_group(domain=sales_domain + [('partner_id', '!=', False)],
            fields=['product_uom_qty', 'price_total'],
            groupby=['partner_id'], orderby='price_total desc', limit=10)
        for customer_line in report_customer_lines:
            order_count = self.env['sale.order'].search_count([('partner_id', '=', customer_line['partner_id'][0]), ('id', 'in', total_orders.ids)])
            dashboard_data_list['top_customers'].append({'id': customer_line['partner_id'][0],
                                                         'name': customer_line['partner_id'][1],
                                                         'count': order_count,
                                                         'sales': customer_line['price_total']})

    def _get_data_for_instance_wise_selling(self, is_general_dashboard, dashboard_data_list, sales_domain, date_from, date_to):
        mk_type_dict = {}
        date_date_from = fields.Date.from_string(date_from)
        date_date_to = fields.Date.from_string(date_to)
        if not is_general_dashboard:
            sale_graph_data = self._compute_sale_graph(date_date_from, date_date_to, sales_domain)
            dashboard_data_list['sale_graph'] = {'series': [{'name': 'Total Amount', 'data': sale_graph_data[1]}], 'categories': sale_graph_data[0]}
        else:
            series_data_list, bar_categories, bar_data = [], [], []
            for mk_instance_id in self:
                instance_name = mk_instance_id.name
                sale_graph_data = self._compute_sale_graph(date_date_from, date_date_to, [('state', 'in', ['sale', 'done']), ('mk_instance_id', '=', mk_instance_id.id)])
                series_data_list.append({'name': instance_name, 'data': sale_graph_data[1]})
                instance_bar_total_selling = round(sum(sale_graph_data[1]), 2)
                if instance_bar_total_selling:
                    bar_data.append({'name': instance_name, 'data': [instance_bar_total_selling]})
                    bar_categories.append(instance_name)

            dashboard_data_list['sale_graph'] = {'series': series_data_list, 'categories': sale_graph_data[0]}
            dashboard_data_list['bar_graph'] = {'series': bar_data, 'categories': bar_categories}

            # Marketplace Type wise selling
            mk_type_data = self.env['sale.report'].read_group(domain=sales_domain,
                fields=['marketplace_type', 'price_total'],
                groupby='marketplace_type', orderby='price_total desc', limit=5)
            [mk_type_dict.update({dict(self._fields['marketplace'].selection).get(mk_type_line['marketplace_type']): mk_type_line['price_total']}) for mk_type_line in mk_type_data]
            dashboard_data_list['mk_revenue_pieChart'] = {'series': list(mk_type_dict.values()), 'labels': list(mk_type_dict.keys())}
        return dashboard_data_list

    def _fetch_country_sales_data_for_dashboard(self, dashboard_data_list, sales_domain):
        country_lines = self.env['sale.report'].read_group(domain=sales_domain, fields=['country_id', 'price_total'], groupby='country_id', orderby='price_total desc', limit=5)
        country_dict = {country_line['country_id'][1]: country_line['price_total'] for country_line in country_lines if country_line.get('country_id')}
        dashboard_data_list['country_graph'] = {'series': list(country_dict.values()), 'labels': list(country_dict.keys())}
        return dashboard_data_list

    def _get_top_5_performing_category_for_dashboard(self, dashboard_data_list, sales_domain):
        category_lines = self.env['sale.report'].read_group(domain=sales_domain, fields=['categ_id', 'price_total'], groupby='categ_id', orderby='price_total desc', limit=5)
        category_dict = {category_line['categ_id'][1]: category_line['price_total'] for category_line in category_lines}
        dashboard_data_list['category_graph'] = {'series': list(category_dict.values()), 'labels': list(category_dict.keys())}
        return dashboard_data_list

    def _fetch_tiles_summary_for_dashboard(self, is_general_dashboard, sales_domain, total_orders, dashboard_data_list, date_from, date_to):
        if not is_general_dashboard:
            total_sales = self.env['sale.report'].read_group(domain=sales_domain, fields=['price_total'], groupby='mk_instance_id')
            total_sales = total_sales[0].get('price_total') if total_sales else 0
            to_ship_domain = [('mk_instance_id', 'in', self.ids)]
        else:
            total_sales = total_orders.mapped('amount_total')
            total_sales = sum(total_sales) if total_sales else 0
            to_ship_domain = [('mk_instance_id', '!=', False), ('mk_instance_id.state', '=', 'confirmed')]

        to_ship_count = self.env['stock.picking'].search_count(to_ship_domain + [('state', 'not in', ['cancel', 'done']), ('create_date', '>=', date_from), ('create_date', '<=', date_to)])
        dashboard_data_list['summary']['total_orders'] = len(total_orders)
        dashboard_data_list['summary']['pending_shipments'] = to_ship_count
        dashboard_data_list['summary']['total_sales'] = total_sales
        dashboard_data_list['summary']['avg_order_value'] = total_sales / (len(total_orders) or 1)
        return dashboard_data_list

    def get_previous_date_range(self, start_date, end_date, interval):
        if interval in ['this_month', 'last_month']:
            previous_start_date = start_date - relativedelta(months=1)
            previous_end_date = end_date - relativedelta(months=1)
        elif interval in ['this_year', 'last_year']:
            previous_start_date = start_date - relativedelta(years=1)
            previous_end_date = end_date - relativedelta(years=1)
        elif interval == ['this_quarter', 'last_quarter']:
            previous_start_date = start_date - relativedelta(months=3)
            previous_end_date = end_date - relativedelta(months=3)
        else:
            previous_start_date = start_date - timedelta(days=1)
            previous_end_date = previous_start_date - (end_date - start_date)
        return previous_start_date, previous_end_date

    def _fetch_kpi_tiles_summary_for_dashboard(self, is_general_dashboard, dashboard_data_list, dates_ranges, interval):
        date_from, date_to = self.get_previous_date_range(dates_ranges.get('date_from'), dates_ranges.get('date_to'), interval)
        total_orders = self.env['sale.order'].search([('date_order', '>=', date_to), ('date_order', '<=', date_from), ('state', 'in', ['sale', 'done']), ('mk_instance_id', 'in', self.ids)], order="date_order")
        sales_domain = [('state', 'in', ['sale', 'done']), ('order_id', 'in', total_orders.ids), ('date', '>=', date_to), ('date', '<=', date_from)]
        if not is_general_dashboard:
            total_sales = self.env['sale.report'].read_group(domain=sales_domain, fields=['price_total'], groupby='mk_instance_id')
            total_sales = total_sales[0].get('price_total') if total_sales else 0
            to_ship_domain = [('mk_instance_id', 'in', self.ids)]
        else:
            total_sales = total_orders.mapped('amount_total')
            total_sales = sum(total_sales) if total_sales else 0
            to_ship_domain = [('mk_instance_id', '!=', False), ('mk_instance_id.state', '=', 'confirmed')]

        to_ship_count = self.env['stock.picking'].search_count(to_ship_domain + [('state', 'not in', ['cancel', 'done']), ('create_date', '>=', date_to), ('create_date', '<=', date_from)])
        kpi_total_orders = self._get_margin_value(dashboard_data_list['summary']['total_orders'], len(total_orders))
        kpi_pending_shipments = self._get_margin_value(dashboard_data_list['summary']['pending_shipments'], to_ship_count)
        kpi_total_sales = self._get_margin_value(dashboard_data_list['summary']['total_sales'], total_sales)
        kpi_avg_order_value = self._get_margin_value(dashboard_data_list['summary']['avg_order_value'], total_sales / (len(total_orders) or 1))
        dashboard_data_list['summary']['kpi_total_orders'] = round(kpi_total_orders, 2)
        dashboard_data_list['summary']['kpi_pending_shipments'] = round(kpi_pending_shipments, 2)
        dashboard_data_list['summary']['kpi_total_sales'] = round(kpi_total_sales, 2)
        dashboard_data_list['summary']['kpi_avg_order_value'] = round(kpi_avg_order_value, 2)
        return dashboard_data_list

    def get_mk_dashboard_data(self, date_from, date_to, dates_ranges, date_filter, is_general_dashboard=True):
        dashboard_data_list = dict(currency_id=self.env.user.company_id.currency_id.id, is_general_dashboard=is_general_dashboard, sale_graph=[], best_sellers=[], top_customers=[], category_graph=[], country_graph=[], summary=dict(total_orders=0, total_sales=0, pending_shipments=0, avg_order_value=0))

        total_orders = self.env['sale.order'].search([('date_order', '>=', date_from), ('date_order', '<=', date_to), ('state', 'in', ['sale', 'done']),
                                                      ('mk_instance_id', 'in', self.ids)], order="date_order")
        if not date_from or not date_to or not self:
            return dashboard_data_list

        sales_domain = [('state', 'in', ['sale', 'done']), ('order_id', 'in', total_orders.ids), ('date', '>=', date_from), ('date', '<=', date_to)]

        # Product-based computation
        self._get_top_10_performing_products(dashboard_data_list, sales_domain)

        # Customer-based computation
        self._get_top_10_customers(total_orders, dashboard_data_list, sales_domain)

        # Sale Graph
        self._get_data_for_instance_wise_selling(is_general_dashboard, dashboard_data_list, sales_domain, date_from, date_to)

        # Country wise selling
        self._fetch_country_sales_data_for_dashboard(dashboard_data_list, sales_domain)

        # Category wise selling
        self._get_top_5_performing_category_for_dashboard(dashboard_data_list, sales_domain)

        # Tiles Summery
        self._fetch_tiles_summary_for_dashboard(is_general_dashboard, sales_domain, total_orders, dashboard_data_list, date_from, date_to)

        # KPI for Tiles Summery
        if not dates_ranges:
            dates_ranges = {'date_from': fields.Date.from_string(date_from), 'date_to': fields.Date.from_string(date_to)}
        self._fetch_kpi_tiles_summary_for_dashboard(is_general_dashboard, dashboard_data_list, dates_ranges, date_filter)
        return dashboard_data_list

    def _compute_sale_graph(self, date_from, date_to, sales_domain, previous=False):
        days_between = (date_to - date_from).days
        date_list = [(date_from + timedelta(days=x)) for x in range(0, days_between + 1)]

        daily_sales = self.env['sale.report'].read_group(domain=sales_domain,
                                                         fields=['date', 'price_subtotal'],
                                                         groupby='date:day')

        daily_sales_dict = {p['date:day']: p['price_subtotal'] for p in daily_sales}

        sales_graph = [{
            '0': fields.Date.to_string(d) if not previous else fields.Date.to_string(d + timedelta(days=days_between)),
            # Respect read_group format in models.py
            '1': daily_sales_dict.get(babel.dates.format_date(d, format='dd MMM yyyy', locale=self.env.context.get('lang') or 'en_US'), 0)
        } for d in date_list]
        date_range = [item.get('0') for item in sales_graph]
        sale_amount = [item.get('1') for item in sales_graph]
        if len(date_range) == 1:  # FIX ME: Sale chart has facing issue of not showing line if date range is only one day. Apply temp fix for this.
            next_date = fields.Date.to_string(fields.Date.from_string(date_range[0]) + timedelta(1))
            date_range = date_range + [next_date]
            sale_amount = sale_amount + [0.0]
        return [date_range, sale_amount]

    def has_single_date_filter(self, options):
        return options['date'].get('date_from') is None

    def _get_dates_previous_period(self, options, period_vals):
        period_type = period_vals['period_type']
        date_from = period_vals['date_from']
        date_to = period_vals['date_to']

        if not date_from or not date_to:
            date = (date_from or date_to).replace(day=1) - timedelta(days=1)
            return self._get_dates_period(options, None, date, period_type=period_type)

        date_to = date_from - timedelta(days=1)
        if period_type == 'fiscalyear':
            company_fiscalyear_dates = self.env.user.company_id.compute_fiscalyear_dates(date_to)
            return self._get_dates_period(options, company_fiscalyear_dates['date_from'], company_fiscalyear_dates['date_to'])
        if period_type == 'month':
            return self._get_dates_period(options, *date_utils.get_month(date_to), period_type='month')
        if period_type == 'quarter':
            return self._get_dates_period(options, *date_utils.get_quarter(date_to), period_type='quarter')
        if period_type == 'year':
            return self._get_dates_period(options, *date_utils.get_fiscal_year(date_to), period_type='year')
        date_from = date_to - timedelta(days=(date_to - date_from).days)
        return self._get_dates_period(options, date_from, date_to)

    def _get_dates_period(self, options, date_from, date_to, period_type=None):
        def match(dt_from, dt_to):
            if self.has_single_date_filter(options):
                return (date_to or date_from) == dt_to
            else:
                return (dt_from, dt_to) == (date_from, date_to)

        string = None
        if not period_type:
            date = date_to or date_from
            company_fiscalyear_dates = self.env.user.company_id.compute_fiscalyear_dates(date)
            if match(company_fiscalyear_dates['date_from'], company_fiscalyear_dates['date_to']):
                period_type = 'fiscalyear'
                if company_fiscalyear_dates.get('record'):
                    string = company_fiscalyear_dates['record'].name
            elif match(*date_utils.get_month(date)):
                period_type = 'month'
            elif match(*date_utils.get_quarter(date)):
                period_type = 'quarter'
            elif match(*date_utils.get_fiscal_year(date)):
                period_type = 'year'
            else:
                period_type = 'custom'

        if not string:
            fy_day = self.env.user.company_id.fiscalyear_last_day
            fy_month = int(self.env.company.fiscalyear_last_month)
            if self.has_single_date_filter(options):
                string = _('As of %s') % (format_date(self.env, date_to.strftime(DEFAULT_SERVER_DATE_FORMAT)))
            elif period_type == 'year' or (period_type == 'fiscalyear' and (date_from, date_to) == date_utils.get_fiscal_year(date_to)):
                string = date_to.strftime('%Y')
            elif period_type == 'fiscalyear' and (date_from, date_to) == date_utils.get_fiscal_year(date_to, day=fy_day, month=fy_month):
                string = '%s - %s' % (date_to.year - 1, date_to.year)
            elif period_type == 'month':
                string = format_date(self.env, date_to.strftime(DEFAULT_SERVER_DATE_FORMAT), date_format='MMM YYYY')
            elif period_type == 'quarter':
                quarter_names = get_quarter_names('abbreviated', locale=self.env.context.get('lang') or 'en_US')
                string = u'%s\N{NO-BREAK SPACE}%s' % (quarter_names[date_utils.get_quarter_number(date_to)], date_to.year)
            else:
                dt_from_str = format_date(self.env, date_from.strftime(DEFAULT_SERVER_DATE_FORMAT))
                dt_to_str = format_date(self.env, date_to.strftime(DEFAULT_SERVER_DATE_FORMAT))
                string = _('From %s \n to  %s') % (dt_from_str, dt_to_str)
                if options['date'].get('filter', '') == 'today':
                    string = 'Today'

        return {
            'string': string,
            'period_type': period_type,
            'date_from': date_from,
            'date_to': date_to,
        }

    def _apply_date_filter(self, options):
        def create_vals(period_vals):
            vals = {'string': period_vals['string']}
            if self.has_single_date_filter(options):
                vals['date'] = (period_vals['date_to'] or period_vals['date_from']).strftime(DEFAULT_SERVER_DATE_FORMAT)
            else:
                vals['date_from'] = period_vals['date_from'].strftime(DEFAULT_SERVER_DATE_FORMAT)
                vals['date_to'] = period_vals['date_to'].strftime(DEFAULT_SERVER_DATE_FORMAT)
            return vals

        # Date Filter
        if not options.get('date') or not options['date'].get('filter'):
            return
        options_filter = options['date']['filter']

        date_from = None
        date_to = date.today()
        if options_filter == 'custom':
            if self.has_single_date_filter(options):
                date_from = None
                date_to = fields.Date.from_string(options['date']['date'])
            else:
                date_from = fields.Date.from_string(options['date']['date_from'])
                date_to = fields.Date.from_string(options['date']['date_to'])
        elif 'today' in options_filter:
            if not self.has_single_date_filter(options):
                date_from = date.today()
        elif 'month' in options_filter:
            date_from, date_to = date_utils.get_month(date_to)
        elif 'quarter' in options_filter:
            date_from, date_to = date_utils.get_quarter(date_to)
        elif 'year' in options_filter:
            company_fiscalyear_dates = self.env.user.company_id.compute_fiscalyear_dates(date_to)
            date_from = company_fiscalyear_dates['date_from']
            date_to = company_fiscalyear_dates['date_to']
        else:
            raise UserError('Programmatic Error: Unrecognized parameter %s in date filter!' % str(options_filter))

        period_vals = self._get_dates_period(options, date_from, date_to)
        if 'last' in options_filter:
            period_vals = self._get_dates_previous_period(options, period_vals)
        if 'today' in options_filter:
            options['date']['string'] = 'Today'
        options['date'].update(create_vals(period_vals))
        return

    @api.model
    def _get_options(self, previous_options=None):
        if not previous_options:
            previous_options = {}
        options = {}
        filter_list = ['filter_date']
        for element in filter_list:
            filter_name = element[7:]
            options[filter_name] = getattr(self, element)

        for key, value in options.items():
            if key in previous_options and value is not None and previous_options[key] is not None:
                if key == 'date' or key == 'comparison':
                    if key == 'comparison':
                        options[key]['number_period'] = previous_options[key]['number_period']
                    options[key]['filter'] = 'custom'
                    if previous_options[key].get('filter', 'custom') != 'custom':
                        options[key]['filter'] = previous_options[key]['filter']
                    elif value.get('date_from') is not None and not previous_options[key].get('date_from'):
                        date = fields.Date.from_string(previous_options[key]['date'])
                        company_fiscalyear_dates = self.env.user.company_id.compute_fiscalyear_dates(date)
                        options[key]['date_from'] = company_fiscalyear_dates['date_from'].strftime(DEFAULT_SERVER_DATE_FORMAT)
                        options[key]['date_to'] = previous_options[key]['date']
                    elif value.get('date') is not None and not previous_options[key].get('date'):
                        options[key]['date'] = previous_options[key]['date_to']
                    else:
                        options[key] = previous_options[key]
                else:
                    options[key] = previous_options[key]
        return options

    def get_mk_dashboard_informations(self, options):
        '''
        return a dictionary of information that will be needed by the js widget searchview, ...
        '''
        options = self._get_options(options)

        self._apply_date_filter(options)

        searchview_dict = {'options': options, 'context': self.env.context}

        info = {'options': options,
                'context': self.env.context,
                'searchview_html': self.env['ir.ui.view']._render_template('base_marketplace.search_template', values=searchview_dict)}
        return info

    @api.model
    def _get_mk_dashboard_dates_ranges(self):
        today = fields.Date.context_today(self)

        is_account_present = hasattr(self.env.company, 'compute_fiscalyear_dates')
        this_year = {'date_from': date(today.year, 1, 1), 'date_to': date(today.year, 12, 31)}
        last_year = {'date_from': date(today.year - 1, 1, 1), 'date_to': date(today.year - 1, 12, 31)}

        this_year_dates = self.env.company.compute_fiscalyear_dates(today) if is_account_present else this_year
        last_year_dates = self.env.company.compute_fiscalyear_dates(today - relativedelta(years=1)) if is_account_present else last_year

        this_quarter_from, this_quarter_to = date_utils.get_quarter(today)
        last_quarter_from, last_quarter_to = date_utils.get_quarter(today - relativedelta(months=3))

        this_month_from, this_month_to = date_utils.get_month(today)
        last_month_from, last_month_to = date_utils.get_month(today - relativedelta(months=1))
        return {
            'this_year': {'date_from': this_year_dates['date_from'], 'date_to': this_year_dates['date_to']},
            'last_year': {'date_from': last_year_dates['date_from'], 'date_to': last_year_dates['date_to']},
            'this_quarter': {'date_from': this_quarter_from, 'date_to': this_quarter_to},
            'last_quarter': {'date_from': last_quarter_from, 'date_to': last_quarter_to},
            'this_month': {'date_from': this_month_from, 'date_to': this_month_to},
            'last_month': {'date_from': last_month_from, 'date_to': last_month_to},
        }

    def check_instance_pricelist(self, currency_id):
        if self.pricelist_id:
            instance_currency_id = self.pricelist_id.currency_id
            if instance_currency_id != currency_id:
                raise ValidationError(_("Pricelist's currency and currency get from Marketplace is not same. Marketplace Currency: {}".format(currency_id.name)))
        return True

    def create_pricelist(self, currency_id):
        pricelist_vals = {'name': "{}: {}".format(self.marketplace.title(), self.name),
                          'currency_id': currency_id.id,
                          'company_id': self.company_id.id}
        pricelist_id = self.env['product.pricelist'].create(pricelist_vals)
        return pricelist_id

    def set_pricelist(self, currency_name):
        currency_obj = self.env['res.currency']
        currency_id = currency_obj.search([('name', '=', currency_name)])
        if not currency_id:
            currency_id = currency_obj.search([('name', '=', currency_name), ('active', '=', False)])
            if currency_id:
                currency_id.write({'active': True})
        if not self.check_instance_pricelist(currency_id):
            raise ValidationError(_("Set Pricelist currency {} is not match with {} Store Currency {}".format(self.pricelist_id.currency_id.name, self.marketplace.title(), currency_name)))
        if not self.pricelist_id:
            pricelist_id = self.create_pricelist(currency_id)
            if not pricelist_id:
                raise ValidationError(_("Please set pricelist manually with currency: {}".format(currency_id.name)))
            self.pricelist_id = pricelist_id.id
        return True

    def get_fields_for_hide(self):
        marketplace_list = self.env['mk.instance'].get_all_marketplace()
        field_dict = {}
        for marketplace in marketplace_list:
            if hasattr(self, '%s_hide_fields' % marketplace):
                field_list = getattr(self, '%s_hide_fields' % marketplace)()
                field_dict.update({marketplace: field_list})
        return field_dict

    def get_page_for_hide(self):
        marketplace_list = self.env['mk.instance'].get_all_marketplace()
        page_dict = {}
        for marketplace in marketplace_list:
            if hasattr(self, '%s_hide_page' % marketplace):
                page_list = getattr(self, '%s_hide_page' % marketplace)()
                page_dict.update({marketplace: page_list})
        return page_dict

    def get_instance_fields_for_hide(self):
        marketplace_list = self.env['mk.instance'].get_all_marketplace()
        # values = dict((field, getattr(template, field)) for field in fields if getattr(template, field))
        instance_field_dict = {}
        for marketplace in marketplace_list:
            if hasattr(self, '%s_hide_instance_field' % marketplace):
                instance_field_list = getattr(self, '%s_hide_instance_field' % marketplace)()
                instance_field_dict.update({marketplace: instance_field_list})
        return instance_field_dict

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        ret_val = super(MkInstance, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        need_to_hide_field_dict = self.get_fields_for_hide()
        doc = etree.XML(ret_val['arch'])
        if view_type == 'form':
            # For hide page
            need_to_hide_page_list = self.get_page_for_hide()
            for marketplace, instance_field_list in need_to_hide_page_list.items():
                for page in instance_field_list:
                    for node in doc.xpath("//page[@name='%s']" % page):
                        existing_domain, new_domain = [], []
                        if not node.get("modifiers"):
                            node.set("modifiers", json.dumps({'invisible': [('marketplace', '=', marketplace)]}))
                            continue
                        modifiers = json.loads(node.get("modifiers"))
                        if 'invisible' in modifiers and isinstance(modifiers['invisible'], list):
                            if not existing_domain:
                                existing_domain = modifiers['invisible']
                            if not new_domain:
                                new_domain = [('marketplace', '=', marketplace)]
                            else:
                                new_domain = expression.OR([new_domain, [('marketplace', '=', marketplace)]])
                        else:
                            modifiers['invisible'] = [('marketplace', '=', marketplace)]
                        node.set("modifiers", json.dumps(modifiers))
                        if existing_domain and new_domain:
                            node.set("modifiers", json.dumps({'invisible': expression.OR([existing_domain, new_domain])}))
            # For hide instance fields.
            need_to_hide_instance_fields_list = self.get_instance_fields_for_hide()
            for marketplace, instance_field_list in need_to_hide_instance_fields_list.items():
                for instance_field in instance_field_list:
                    for node in doc.xpath("//div[@name='%s']" % instance_field):
                        existing_domain, new_domain = [], []
                        if not node.get("modifiers"):
                            node.set("modifiers", json.dumps({'invisible': [('marketplace', '=', marketplace)]}))
                            continue
                        modifiers = json.loads(node.get("modifiers"))
                        if 'invisible' in modifiers and isinstance(modifiers['invisible'], list):
                            if not existing_domain:
                                existing_domain = modifiers['invisible']
                            if not new_domain:
                                new_domain = [('marketplace', '=', marketplace)]
                            else:
                                new_domain = expression.OR([new_domain, [('marketplace', '=', marketplace)]])
                        else:
                            modifiers['invisible'] = [('marketplace', '=', marketplace)]
                        node.set("modifiers", json.dumps(modifiers))
                        if existing_domain and new_domain:
                            node.set("modifiers", json.dumps({'invisible': expression.OR([existing_domain, new_domain])}))
        for field in ret_val['fields']:
            for node in doc.xpath("//field[@name='%s']" % field):
                existing_domain, new_domain = [], []
                for marketplace, field_list in need_to_hide_field_dict.items():
                    if field in field_list:
                        modifiers = json.loads(node.get("modifiers"))
                        if 'invisible' in modifiers and isinstance(modifiers['invisible'], list):
                            if not existing_domain:
                                existing_domain = modifiers['invisible']
                            if not new_domain:
                                new_domain = [('marketplace', '=', marketplace)]
                            else:
                                new_domain = expression.OR([new_domain, [('marketplace', '=', marketplace)]])
                        else:
                            modifiers['invisible'] = [('marketplace', '=', marketplace)]
                        node.set("modifiers", json.dumps(modifiers))
                if existing_domain and new_domain:
                    node.set("modifiers", json.dumps({'invisible': expression.OR([existing_domain, new_domain])}))
        ret_val['arch'] = etree.tostring(doc, encoding='unicode')
        return ret_val

    def create_update_schedule_actions(self):
        self.env['ir.cron'].setup_schedule_actions(self)

    def action_open_model_view(self, res_id_list, model_name, action_name):
        if not res_id_list:
            return False
        action = {'res_model': model_name, 'type': 'ir.actions.act_window', 'target': 'current'}
        if len(res_id_list) == 1:
            action.update({'view_mode': 'form', 'res_id': res_id_list[0]})
        else:
            action.update({'name': _(action_name), 'domain': [('id', 'in', res_id_list)], 'view_mode': 'tree,form'})
        return action
