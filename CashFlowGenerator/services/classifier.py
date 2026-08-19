# src/services/classifier.py - 修复版
"""交易分类服务"""

from typing import List, Optional

from models.transaction import Transaction, ClassifiedTransaction
from CashFlowGenerator.config import Config


class TransactionClassifier:
    """交易分类器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.classification_config = config.data.classification
    
    def classify(self, transaction: Transaction) -> Optional[ClassifiedTransaction]:
        """分类单笔交易"""
        is_income = transaction.is_income
        
        if is_income:
            # 所有收入统一归入其他收入
            category = self.classification_config.default_income_category
        else:
            contra = getattr(transaction, 'contra_subject', "") or ""
            desc = transaction.description or ""
            category = self.classification_config.get_category_by_contra(contra, desc, is_income=False)
            if not category:
                category = self.classification_config.default_expense_category
        
        return ClassifiedTransaction(
            date=transaction.date,
            voucher=transaction.voucher,
            description=transaction.description,
            debit=transaction.debit,
            credit=transaction.credit,
            contra_subject=getattr(transaction, 'contra_subject', ""),
            amount=transaction.amount,
            is_income=transaction.is_income,
            sheet_name=getattr(transaction, 'sheet_name', ""),
            row_index=getattr(transaction, 'row_index', -1),
            balance=getattr(transaction, 'balance', None),
            income_category=category if is_income else None,
            expense_category=None if is_income else category,
            classification_confidence=0.8
        )
    
    def classify_batch(self, transactions: List[Transaction]) -> List[ClassifiedTransaction]:
        """批量分类交易"""
        return [self.classify(t) for t in transactions if t]