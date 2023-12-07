3.8.4 (23-Oct-2023)

- Now support Fulfillable Custom Order lines.
- Support duties.

3.8.3 (28-Sep-2023)

- Ability to enable/disable credit note creation.

3.8.2 (22-Sep-2023)

- Can see Inventory from listing item view based on Inventory management and Location setting.
- Update Tags while update orders in Odoo.
- Improve code of retry failed queue line.
- Skip auto create credit note if there are any discrepancy.

3.8.1 (15-Sep-2023)

- Import Order tags.
- Improve code for default product set.

3.8 (05-Sep-2023)

- Fixed multiple payment register issue.

3.7.9 (22-Aug-2023)

- Process draft order based on workflow.

3.7.8 (08-Aug-2023)

- Added Delete Webhook button.
- Update Webhook process.

3.7.7 (31-July-2023)

- Manage exception for no customer in the order.

3.7.6 (17-July-2023)

- Added 10-minute buffer time while import orders.
- Introduce automatic credit note create in Odoo.
- Validation for Quality check while validate delivery order.

3.7.5 (05-July-2023)

- Added new condition in for Shopify Collection.

3.7.4 (06-June-2023)

- Change the position of default product configurations.
- Added Company in the Shopify Financial Work flow.
- Users can now create payment gateways manually.

3.7.3 (01-June-2023)

- Added Configure Workflow button in the Log line. 
- Take only Sale and Capture kind of transactions while reconcile invoice. 
- Fixed minor bugs of Payout. 

3.7.2 (31-May-2023)

- Improved Webhook process.

3.7.1 (25-May-2023)

- Improvement and added extra features.

3.7 (24-May-2023)

- Major improvement and bug fixes.
- Introduce Shopify Payout.

3.6.1 (22-May-2023)

- Improve code to Fulfill drop-ship delivery Orders if later on order is fulfilled in Shopify.
- Fixed issue of not update listings if it is imported from order import process.

3.6 (18-May-2023)

- Fulfill Order if later on order is fulfilled in Shopify.

3.5 (27-April-2023)

- Improved Shopify fulfillment process.

3.4 (08-April-2023)

- Improved Shopify Location Import process.

3.3 (13-Feb-2023)

- Improved Code.
- Improved refund code.
- Customer can now select use marketplace currency or company currency.

3.2 (23-Jan-2023)

- Update Shopify SDK (version 12.2.0)

3.1 (30-Dec-2022)

- Automatic fulfill already imported orders using update orders webhook.

3.0 (04-Oct-2022)

- Added Order Import After Date in the Instance Configuration.

2.9 (23-Sep-2022)

- Fixed issue of refund order.

2.8 (19-Sep-2022)

- Fixed issue of register payment.

2.7 (06-Sep-2022)

- Improve Refund Process
- Improve Stock update process from Odoo to Shopify

2.6

- Changes tax calculation value according to Base Marketplace.
- Fetch only success transactions from Shopify.
- Improved code of refund.

2.5

- Update the product sku or barcode if not set while import listing process.
- Get transactions of order from shopify if context in not get the transactions while process of reconcile invoice.
- Fixed issue of set wrong warehouse set in the order.

2.4

- Improve the Shopify import order process.

2.3

- Added shopify last stock update on(datetime) field and update that field while update listing item stock Odoo to
  Shopify.
- Improve the Shopify API calls limit.

2.2

- Multi-currency in sales orders.

2.1

- Improved Shopify Authentication process.

  2.0
- Added Update Order Status in Marketplace in Pickings.
- Change flow of fulfillment. Before fulfillment update location of order.

1.9

- Do not create taxes if set Default Tax System to Odoo's Default Tax Behaviour.

1.8

- While performing Update Order Status if tracking url is present than we also sent tracking url.

1.7

- User can now select/change Weight Unit from Listing Item.
- Schedule action for update product price.
- Limit export listing process to 80.

1.6

- Fixed issue of not webhook.
- Sometime Charge tax on product is not working so fixed that issue.
- Added Tip and Gift Card product configuration in Instance.
- You can define Order prefix as well.

1.5

- Modified tax system of orders according to Tax System configured in instance.

1.4

- Added Access token in Shopify instance configuration.

1.3

- Updated Shopify Python SDK Version.

1.2

- Fixed issue while using third party Fulfillment Service and import Listings.

1.1:

- Initial Release

