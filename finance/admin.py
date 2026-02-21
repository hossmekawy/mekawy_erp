from django.contrib import admin
from .models import Account, Transaction, CashCount, CustodyHandover

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    """
    Configuration for the Account model in the Django admin interface.
    """
    list_display = ('name', 'account_type', 'balance', 'manufacturer')
    list_filter = ('account_type',)
    search_fields = ('name', 'manufacturer__name')
    readonly_fields = ('balance',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """
    Configuration for the Transaction model in the Django admin interface.
    """
    list_display = ('timestamp', 'type', 'account', 'to_account', 'amount', 'description')
    list_filter = ('type', 'account')
    search_fields = ('description', 'reference', 'account__name', 'to_account__name')
    autocomplete_fields = ('account', 'to_account')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'

@admin.register(CashCount)
class CashCountAdmin(admin.ModelAdmin):
    """
    Configuration for the CashCount model in the Django admin interface.
    Allows for easy viewing of treasury stocktaking records.
    """
    list_display = ('timestamp', 'account', 'counted_amount', 'actual_balance', 'difference', 'user')
    list_filter = ('account', 'user')
    date_hierarchy = 'timestamp'
    readonly_fields = ('timestamp', 'actual_balance', 'difference')

@admin.register(CustodyHandover)
class CustodyHandoverAdmin(admin.ModelAdmin):
    """
    Configuration for the CustodyHandover model in the Django admin interface.
    Provides a clear audit trail of custody transfers.
    """
    list_display = ('timestamp', 'account', 'amount_handed_over', 'from_user', 'to_user')
    list_filter = ('account', 'from_user', 'to_user')
    date_hierarchy = 'timestamp'
    readonly_fields = ('timestamp',)
    autocomplete_fields = ('account', 'from_user', 'to_user')
