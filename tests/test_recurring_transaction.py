import calendar
from datetime import datetime, timedelta
from pydantic import ValidationError
import pytest
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, patch
from uuid import uuid4
import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from src.app.schemas.transaction import RecurringTransactionCreate, TransactionCreate
from src.app.services.crud.recurring_transaction import create_recurring_transaction, process_recurring_transactions, \
    cancel_recurring_transaction, get_recurring_transactions
from src.app.sql_app.models.enumerate import IntervalType
from src.app.sql_app.models.models import Card, User, Wallet, RecurringTransaction


@pytest.mark.asyncio
async def test_create_recurring_transaction_success():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"

    transaction_data = RecurringTransactionCreate(
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency)
    card = Card(id=card_id, user_id=sender_id)
    recipient_wallet = Wallet(user_id=recipient_id, currency=currency)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    new_transaction = await create_recurring_transaction(db, transaction_data, sender_id)

    assert new_transaction.user_id == sender_id
    assert new_transaction.card_id == card_id
    assert new_transaction.recipient_id == recipient_id
    assert new_transaction.amount == transaction_data.amount
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(new_transaction)


@pytest.mark.asyncio
async def test_create_recurring_transaction_sender_not_found():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    currency = "USD"
    transaction_data = RecurringTransactionCreate(
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency
    )

    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))))

    with pytest.raises(HTTPException) as exc_info:
        await create_recurring_transaction(db, transaction_data, sender_id)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Sender not found."


@pytest.mark.asyncio
async def test_create_recurring_transaction_sender_blocked():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    currency = "USD"
    transaction_data = RecurringTransactionCreate(
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=True)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender))))
    ])

    with pytest.raises(HTTPException) as exc_info:
        await create_recurring_transaction(db, transaction_data, sender_id)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Sender is blocked."


@pytest.mark.asyncio
async def test_create_recurring_transaction_sender_wallet_not_found():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    currency = "USD"
    transaction_data = RecurringTransactionCreate(
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
    ])

    with pytest.raises(HTTPException) as exc_info:
        await create_recurring_transaction(db, transaction_data, sender_id)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Sender's wallet in the specified currency not found."


@pytest.mark.asyncio
async def test_create_recurring_transaction_insufficient_funds():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    currency= "USD"
    transaction_data = RecurringTransactionCreate(
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=50.0)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet))))
    ])

    with pytest.raises(HTTPException) as exc_info:
        await create_recurring_transaction(db, transaction_data, sender_id)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Insufficient funds."


@pytest.mark.asyncio
async def test_create_recurring_transaction_card_not_found():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    currency = "USD"
    transaction_data = RecurringTransactionCreate(
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
    ])

    with pytest.raises(HTTPException) as exc_info:
        await create_recurring_transaction(db, transaction_data, sender_id)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Card not found."


@pytest.mark.asyncio
async def test_create_recurring_transaction_recipient_wallet_not_found():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    currency = "USD"

    transaction_data = RecurringTransactionCreate(
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0)
    card = Card(id=transaction_data.card_id, user_id=sender_id)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
    ])

    with pytest.raises(HTTPException) as exc_info:
        await create_recurring_transaction(db, transaction_data, sender_id)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Recipient's wallet not found."

@pytest.mark.asyncio
async def test_create_recurring_transaction_interval_types():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"

    interval_types = ["daily", "weekly", "monthly"]
    for interval_type in interval_types:
        transaction_data = RecurringTransactionCreate(
            card_id=card_id,
            recipient_id=recipient_id,
            category_id=uuid4(),
            amount=100.0,
            interval=30,
            interval_type=interval_type,
            next_execution_date="2024-06-01",
            currency=currency
        )

        sender = User(id=sender_id, is_blocked=False)
        sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency)
        card = Card(id=card_id, user_id=sender_id)
        recipient_wallet = Wallet(user_id=recipient_id, currency=currency)

        db.execute = AsyncMock(side_effect=[
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
        ])
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        new_transaction = await create_recurring_transaction(db, transaction_data, sender_id)

        assert new_transaction.interval_type.value == interval_type
        db.commit.assert_called()
        db.refresh.assert_called_with(new_transaction)




@pytest.mark.asyncio
async def test_create_recurring_transaction_invalid_interval_type():
    with pytest.raises(ValidationError) as exc_info:
        transaction_data = RecurringTransactionCreate(
            card_id=uuid4(),
            recipient_id=uuid4(),
            category_id=uuid4(),
            amount=100.0,
            interval=30,
            interval_type="invalid",
            next_execution_date="2024-06-01",
            currency="USD"
        )

    assert "Input should be 'daily', 'weekly' or 'monthly'" in str(exc_info.value)



@pytest.mark.asyncio
async def test_no_due_transactions():
    db = AsyncMock(spec=AsyncSession)
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []

    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=mock_scalars)))

    await process_recurring_transactions(db)

    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_process_due_recurring_transactions():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"
    current_time = datetime.now(pytz.utc)

    recurring_transaction = RecurringTransaction(
        id=uuid4(),
        user_id=sender_id,
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.DAILY,
        next_execution_date=current_time,
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency)
    recipient_wallet = Wallet(user_id=recipient_id, balance=200.0, currency=currency)
    card = Card(id=card_id, user_id=sender_id)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[recurring_transaction])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    await process_recurring_transactions(db)

    db.commit.assert_called()
    db.refresh.assert_called()
    db.rollback.assert_not_called()



@pytest.mark.asyncio
async def test_cancel_recurring_transaction_success():
    db = AsyncMock(spec=AsyncSession)
    recurring_transaction_id = uuid4()
    user_id = uuid4()

    recurring_transaction = RecurringTransaction(
        id=recurring_transaction_id,
        user_id=user_id,
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.DAILY,
        next_execution_date="2024-06-01",
        currency="USD"
    )

    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recurring_transaction)))))
    db.commit = AsyncMock()

    cancelled_transaction = await cancel_recurring_transaction(db, recurring_transaction_id, user_id)

    assert cancelled_transaction == recurring_transaction
    db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_cancel_recurring_transaction_not_found():
    db = AsyncMock(spec=AsyncSession)
    recurring_transaction_id = uuid4()
    user_id = uuid4()

    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))))

    with pytest.raises(HTTPException) as exc_info:
        await cancel_recurring_transaction(db, recurring_transaction_id, user_id)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Recurring transaction not found."

@pytest.mark.asyncio
async def test_cancel_recurring_transaction_permission_denied():
    db = AsyncMock(spec=AsyncSession)
    recurring_transaction_id = uuid4()
    user_id = uuid4()
    other_user_id = uuid4()

    recurring_transaction = RecurringTransaction(
        id=recurring_transaction_id,
        user_id=other_user_id,
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.DAILY,
        next_execution_date="2024-06-01",
        currency="USD"
    )

    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recurring_transaction)))))

    with pytest.raises(HTTPException) as exc_info:
        await cancel_recurring_transaction(db, recurring_transaction_id, user_id)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "User does not have permission to cancel this recurring transaction."


@pytest.mark.asyncio
async def test_create_recurring_transaction_different_currencies():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    currency_sender = "USD"
    currency_recipient = "EUR"

    transaction_data = RecurringTransactionCreate(
        card_id=uuid4(),
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency_sender
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency_sender)
    card = Card(id=transaction_data.card_id, user_id=sender_id)
    recipient_wallet = Wallet(user_id=recipient_id, currency=currency_recipient)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])

    with pytest.raises(HTTPException) as exc_info:
        await create_recurring_transaction(db, transaction_data, sender_id)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Sender's and recipient's wallets must be in the same currency."

@pytest.mark.asyncio
async def test_create_recurring_transaction_different_currencies():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    currency_sender = "USD"
    currency_recipient = "EUR"

    transaction_data = RecurringTransactionCreate(
        card_id=uuid4(),
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency_sender
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency_sender)
    card = Card(id=transaction_data.card_id, user_id=sender_id)
    recipient_wallet = Wallet(user_id=recipient_id, currency=currency_recipient)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])

    with pytest.raises(HTTPException) as exc_info:
        await create_recurring_transaction(db, transaction_data, sender_id)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Sender's and recipient's wallets must be in the same currency."

@pytest.mark.asyncio
async def test_create_recurring_transaction_db_add_fail():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"

    transaction_data = RecurringTransactionCreate(
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type="daily",
        next_execution_date="2024-06-01",
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency)
    card = Card(id=card_id, user_id=sender_id)
    recipient_wallet = Wallet(user_id=recipient_id, currency=currency)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])
    db.commit = AsyncMock(side_effect=Exception("DB commit failed"))

    with pytest.raises(Exception) as exc_info:
        await create_recurring_transaction(db, transaction_data, sender_id)

    assert str(exc_info.value) == "DB commit failed"
    db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_process_due_recurring_transactions_create_transaction_fail():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"
    current_time = datetime.now(pytz.utc)

    recurring_transaction = RecurringTransaction(
        id=uuid4(),
        user_id=sender_id,
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.DAILY,
        next_execution_date=current_time,
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency)
    recipient_wallet = Wallet(user_id=recipient_id, balance=200.0, currency=currency)
    card = Card(id=card_id, user_id=sender_id)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[recurring_transaction])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    with patch("app.services.crud.recurring_transaction.create_transaction", side_effect=Exception("Transaction creation failed")):
        with pytest.raises(Exception) as exc_info:
            await process_recurring_transactions(db)

        assert str(exc_info.value) == "Transaction creation failed"
        db.rollback.assert_called()

@pytest.mark.asyncio
async def test_process_due_recurring_transactions_multiple():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"
    current_time = datetime.now(pytz.utc)

    recurring_transaction1 = RecurringTransaction(
        id=uuid4(),
        user_id=sender_id,
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.DAILY,
        next_execution_date=current_time,
        currency=currency
    )
    recurring_transaction2 = RecurringTransaction(
        id=uuid4(),
        user_id=sender_id,
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=150.0,
        interval=30,
        interval_type=IntervalType.WEEKLY,
        next_execution_date=current_time,
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=500.0, currency=currency)
    recipient_wallet = Wallet(user_id=recipient_id, balance=200.0, currency=currency)
    card = Card(id=card_id, user_id=sender_id)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[recurring_transaction1, recurring_transaction2])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    await process_recurring_transactions(db)

    db.commit.assert_called()
    db.refresh.assert_called()
    db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_get_recurring_transactions_empty():
    db = AsyncMock(spec=AsyncSession)
    user_id = uuid4()
    current_user = User(id=user_id)

    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    result = await get_recurring_transactions(db, current_user)

    assert result == []
    db.execute.assert_called_once()

@pytest.mark.asyncio
async def test_get_recurring_transactions_multiple():
    db = AsyncMock(spec=AsyncSession)
    user_id = uuid4()
    current_user = User(id=user_id)

    recurring_transaction1 = RecurringTransaction(
        id=uuid4(),
        user_id=user_id,
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.DAILY,
        next_execution_date="2024-06-01",
        currency="USD"
    )
    recurring_transaction2 = RecurringTransaction(
        id=uuid4(),
        user_id=user_id,
        card_id=uuid4(),
        recipient_id=uuid4(),
        category_id=uuid4(),
        amount=150.0,
        interval=30,
        interval_type=IntervalType.WEEKLY,
        next_execution_date="2024-06-01",
        currency="USD"
    )

    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[recurring_transaction1, recurring_transaction2])))))

    result = await get_recurring_transactions(db, current_user)

    assert len(result) == 2
    assert recurring_transaction1 in result
    assert recurring_transaction2 in result
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_process_due_recurring_transactions_exception_handling():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"
    current_time = datetime.now(pytz.utc)

    recurring_transaction = RecurringTransaction(
        id=uuid4(),
        user_id=sender_id,
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.DAILY,
        next_execution_date=current_time,
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency)
    recipient_wallet = Wallet(user_id=recipient_id, balance=200.0, currency=currency)
    card = Card(id=card_id, user_id=sender_id)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[recurring_transaction])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    with patch("app.services.crud.recurring_transaction.create_transaction", side_effect=Exception("Transaction creation failed")):
        with pytest.raises(Exception) as exc_info:
            await process_recurring_transactions(db)

        assert str(exc_info.value) == "Transaction creation failed"
        db.rollback.assert_called()


@pytest.mark.asyncio
async def test_get_recurring_transactions_db_access_issue():
    db = AsyncMock(spec=AsyncSession)
    user_id = uuid4()
    current_user = User(id=user_id)

    db.execute = AsyncMock(side_effect=Exception("Database access error"))

    with pytest.raises(Exception) as exc_info:
        await get_recurring_transactions(db, current_user)

    assert str(exc_info.value) == "Database access error"
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_process_due_recurring_transactions_daily():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"
    current_time = datetime.now(pytz.utc)

    recurring_transaction = RecurringTransaction(
        id=uuid4(),
        user_id=sender_id,
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.DAILY,
        next_execution_date=current_time,
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency)
    recipient_wallet = Wallet(user_id=recipient_id, currency=currency)
    card = Card(id=card_id, user_id=sender_id)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[recurring_transaction])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    with patch("app.services.crud.recurring_transaction.create_transaction", new=AsyncMock()):
        await process_recurring_transactions(db)

    assert recurring_transaction.next_execution_date == current_time + timedelta(days=1)
    db.commit.assert_called()

@pytest.mark.asyncio
async def test_process_due_recurring_transactions_weekly():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"
    current_time = datetime.now(pytz.utc)

    recurring_transaction = RecurringTransaction(
        id=uuid4(),
        user_id=sender_id,
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.WEEKLY,
        next_execution_date=current_time,
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency)
    recipient_wallet = Wallet(user_id=recipient_id, currency=currency)
    card = Card(id=card_id, user_id=sender_id)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[recurring_transaction])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])
    db.commit = AsyncMock()

    with patch("app.services.crud.recurring_transaction.create_transaction", new=AsyncMock()):
        await process_recurring_transactions(db)

    assert recurring_transaction.next_execution_date == current_time + timedelta(weeks=1)
    db.commit.assert_called()



@pytest.mark.asyncio
async def test_process_due_recurring_transactions_monthly():
    db = AsyncMock(spec=AsyncSession)
    sender_id = uuid4()
    recipient_id = uuid4()
    card_id = uuid4()
    currency = "USD"
    current_time = datetime.now(pytz.utc)

    recurring_transaction = RecurringTransaction(
        id=uuid4(),
        user_id=sender_id,
        card_id=card_id,
        recipient_id=recipient_id,
        category_id=uuid4(),
        amount=100.0,
        interval=30,
        interval_type=IntervalType.MONTHLY,
        next_execution_date=current_time,
        currency=currency
    )

    sender = User(id=sender_id, is_blocked=False)
    sender_wallet = Wallet(user_id=sender_id, balance=200.0, currency=currency)
    recipient_wallet = Wallet(user_id=recipient_id, currency=currency)
    card = Card(id=card_id, user_id=sender_id)

    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[recurring_transaction])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sender_wallet)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=card)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=recipient_wallet))))
    ])
    db.commit = AsyncMock()

    with patch("app.services.crud.recurring_transaction.create_transaction", new=AsyncMock()):
        await process_recurring_transactions(db)

    next_month = (current_time.month % 12) + 1
    next_year = current_time.year + (current_time.month // 12)
    last_day_of_next_month = calendar.monthrange(next_year, next_month)[1]
    expected_day = min(current_time.day, last_day_of_next_month)
    expected_date = current_time.replace(month=next_month, year=next_year, day=expected_day)

    assert recurring_transaction.next_execution_date == expected_date
    db.commit.assert_called()
