# src/services/aggregator.py - 删除季度相关逻辑
"""数据聚合服务"""

from typing import List
from decimal import Decimal

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.transaction import ClassifiedTransaction
from models.report_data import ReportData
from CashFlowGenerator.config import Config


class DataAggregator:
    """数据聚合器"""
    
    def __init__(self, config: Config = None):
        self.config = config or Config.get_instance()
        self.classification_config = self.config.data.classification
        self.report_data = ReportData()
        self._transactions = []
        self._category_cache = {}
        self._cache_hits = 0
        self._cache_misses = 0
    
    def aggregate(self, transactions: List) -> ReportData:
        """聚合交易数据"""
        self.report_data = ReportData()
        self._transactions = []
        self._cache_hits = 0
        self._cache_misses = 0
    
        if not transactions:
            print("⚠️ 没有交易数据需要聚合")
            return self.report_data
    
        print(f"📝 处理 {len(transactions)} 笔交易...")
    
        for idx, trans in enumerate(transactions):
            if idx % 50 == 0:
                print(f"  处理进度: {idx}/{len(transactions)}")
            try:
                classified = self._classify_transaction(trans)
                if classified:
                    self.report_data.add_transaction(classified)
                    self._transactions.append(classified)
            except Exception as e:
                print(f"⚠️ 处理第 {idx} 笔交易失败: {e}")
                continue
    
        self.report_data._transactions = self._transactions
    
        if self._cache_hits + self._cache_misses > 0:
            hit_rate = self._cache_hits / (self._cache_hits + self._cache_misses) * 100
            print(f"📊 缓存命中率: {hit_rate:.1f}%")
    
        print(f"✅ 聚合完成，共 {len(self._transactions)} 笔交易")
        return self.report_data 
    
    def _classify_transaction(self, trans) -> ClassifiedTransaction:
        """分类单笔交易"""
        cache_key = (
            trans.is_income,
            getattr(trans, 'contra_subject', '')[:30],
            getattr(trans, 'description', '')[:30],
            round(float(trans.amount), 2)
        )
        
        if cache_key in self._category_cache:
            self._cache_hits += 1
            income_cat, expense_cat = self._category_cache[cache_key]
        else:
            self._cache_misses += 1
            income_cat = None
            expense_cat = None
            if trans.is_income:
                income_cat = self.classification_config.default_income_category
            else:
                expense_cat = self._classify_expense(trans)
            if len(self._category_cache) < 20000:
                self._category_cache[cache_key] = (income_cat, expense_cat)
        
        return ClassifiedTransaction(
            date=trans.date,
            voucher=trans.voucher,
            description=trans.description,
            debit=trans.debit,
            credit=trans.credit,
            contra_subject=getattr(trans, 'contra_subject', ""),
            amount=trans.amount,
            is_income=trans.is_income,
            sheet_name=getattr(trans, 'sheet_name', ""),
            row_index=getattr(trans, 'row_index', -1),
            balance=getattr(trans, 'balance', None),
            income_category=self.classification_config.default_income_category if trans.is_income else income_cat,
            expense_category=expense_cat,
            classification_confidence=0.8
        )
    
    def _classify_expense(self, trans) -> str:
        """分类支出"""
        contra = getattr(trans, 'contra_subject', "") or ""
        desc = trans.description or ""
        category = self.classification_config.get_category_by_contra(contra, desc, is_income=False)
        return category if category else self.classification_config.default_expense_category
    
    def get_column_for_category(self, category: str) -> int:
        return self.classification_config.column_mapping.get(category, None)
    
    def reset(self):
        self.report_data = ReportData()
        self._transactions = []
        self._category_cache = {}
        self._cache_hits = 0
        self._cache_misses = 0