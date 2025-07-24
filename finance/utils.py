# finance/utils.py

from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from .models import Transaction, TransactionDetail, Account
from decimal import Decimal

def create_double_entry_transaction(description, created_by, debit_account, credit_account, amount, date, source_document=None):
    """
    Creates a balanced, double-entry transaction. This is the heart of the accounting system.
    It ensures that for every debit, there is a corresponding credit, and the operation is atomic.

    Args:
        description (str): A clear description of the transaction for auditing.
        created_by (User): The user initiating the transaction.
        debit_account (Account): The account to be debited.
        credit_account (Account): The account to be credited.
        amount (Decimal): The amount of the transaction.
        date (date): The date the transaction occurred.
        source_document (Model instance, optional): The document that triggered this transaction (e.g., Invoice).
    
    Returns:
        Transaction: The created Transaction object.
    
    Raises:
        ValueError: If the amount is not a positive Decimal or if accounts are invalid.
    """
    if not isinstance(amount, Decimal) or amount <= 0:
        raise ValueError("Transaction amount must be a positive Decimal.")
    if not isinstance(debit_account, Account) or not isinstance(credit_account, Account):
        raise ValueError("Invalid debit or credit account provided.")
    if debit_account == credit_account:
        raise ValueError("Debit and credit accounts cannot be the same.")

    with transaction.atomic():
        # Create the main transaction record
        trans = Transaction.objects.create(
            description=description,
            created_by=created_by,
            date=date
        )
        
        # Link to the source document if provided
        if source_document:
            trans.source_content_type = ContentType.objects.get_for_model(source_document)
            trans.source_object_id = source_document.pk
            trans.save()

        # Create the Debit Line
        TransactionDetail.objects.create(
            transaction=trans,
            account=debit_account,
            debit=amount,
            credit=Decimal('0.00')
        )
        
        # Create the Credit Line
        TransactionDetail.objects.create(
            transaction=trans,
            account=credit_account,
            debit=Decimal('0.00'),
            credit=amount
        )
        
    return trans
