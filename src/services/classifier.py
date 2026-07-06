# src/services/classifier.py
"""交易分类服务"""

from typing import List, Optional
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.transaction import Transaction, ClassifiedTransaction
from strategies.classification_strategy import ClassificationStrategy
from config import Config


class TransactionClassifier:
    """交易分类器"""
    
    def __init__(self, strategy: ClassificationStrategy, config: Config):
        self.strategy = strategy
        self.config = config
    
    def classify(self, transaction: Transaction) -> Optional[ClassifiedTransaction]:
        """分类单笔交易"""
        return self.strategy.classify(transaction)
    
    def classify_batch(self, transactions: List[Transaction]) -> List[ClassifiedTransaction]:
        """批量分类交易"""
        classified = []
        for trans in transactions:
            result = self.classify(trans)
            if result:
                classified.append(result)
        return classified