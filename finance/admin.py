# finance/admin.py

from django.contrib import admin
from .models import AccountCategory, Account, Transaction, TransactionDetail, Invoice, Payment, Expense

class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'category', 'balance', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'code')
    readonly_fields = ('balance',)

class TransactionDetailInline(admin.TabularInline):
    model = TransactionDetail
    extra = 0
    readonly_fields = ('account', 'debit', 'credit')

class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'total_debit', 'is_balanced', 'created_by')
    list_filter = ('date', 'created_by')
    search_fields = ('description',)
    inlines = [TransactionDetailInline]
    readonly_fields = ('source_document',)

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ('payment_date', 'amount', 'payment_method')

class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'recipient', 'issue_date', 'due_date', 'total_amount', 'paid_amount', 'balance_due', 'status')
    list_filter = ('status', 'issue_date', 'due_date')
    search_fields = ('invoice_number', 'recipient__name') # Note: This search might need adjustment based on recipient models
    inlines = [PaymentInline]
    readonly_fields = ('paid_amount', 'balance_due')

class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('expense_date', 'description', 'amount', 'expense_account', 'source_account', 'created_by')
    list_filter = ('expense_date', 'expense_account', 'source_account')
    search_fields = ('description',)

admin.site.register(AccountCategory)
admin.site.register(Account, AccountAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(Payment)
admin.site.register(Expense, ExpenseAdmin)
