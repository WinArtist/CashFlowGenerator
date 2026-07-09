# src/services/summary_service.py
"""汇总表服务 - 将多个明细账文件汇总到汇总表"""

from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import re

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils.cell import get_column_letter

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from models.transaction import ClassifiedTransaction
from services.data_loader import DataLoader
from services.aggregator import DataAggregator


class SummaryService:
    """汇总表服务 - 多文件汇总到汇总表"""
    
    # 月份名称列表
    MONTH_NAMES = ['1月', '2月', '3月', '4月', '5月', '6月', 
                   '7月', '8月', '9月', '10月', '11月', '12月']
    
    def __init__(self, config: Config):
        self.config = config
        self.data_loader = DataLoader(config)
        self.aggregator = DataAggregator(config)
        
        # 汇总表的列映射（包含收入和支出）
        self.COL_MAPPING = {
            # 固定列
            '行号': 1,          # A列
            '交易时间': 2,       # B列
            
            # ===== 收入列 (O/P/Q列) =====
            '产品收入': 15,
            '服务收入': 16,
            '其他收入': 17,
            
            # ===== 主营业务支出 (V列开始) =====
            '主营业务支出_商品采购': 22,
            '主营业务支出_运费': 23,
            '主营业务支出_服务费': 24,
            '主营业务支出_返点佣金': 25,
            
            # ===== 研发费用 =====
            '研发费用_人工成本': 26,
            '研发费用_材料设备': 27,
            '研发费用_服务费': 28,
            '研发费用_委外': 29,
            
            # ===== 销售费用 =====
            '销售费用_飞机动车等': 30,
            '销售费用_住宿费': 31,
            '销售费用_车辆费': 32,
            '销售费用_市内交通': 33,
            '销售费用_招待公关': 34,
            '销售费用_服务费': 35,
            '销售费用_经销返点': 36,
            '销售费用_其他': 37,
            
            # ===== 管理费用 =====
            '管理费用_办公费': 38,
            '管理费用_办公租金物业费水电费': 39,
            '管理费用_市内交通': 40,
            '管理费用_招待公关': 41,
            '管理费用_飞机动车等': 42,
            '管理费用_人员薪资': 43,
            '管理费用_社保公积金': 44,
            '管理费用_员工福利': 45,
            '管理费用_其他': 46,
            
            # ===== 财务费用 =====
            '财务费用_手续费': 47,
            '财务费用_结息': 48,
            '财务费用_贷款利息': 49,
            
            # ===== 应缴税金 =====
            '应缴税金_增值税及附加': 50,
            '应缴税金_所得税': 51,
            '应缴税金_印花税': 52,
            '应缴税金_工资个税': 53,
            '应缴税金_劳务个税': 54,
            
            # ===== 有形资产 =====
            '有形资产_办公设备': 55,
            '有形资产_办公家具包含车': 56,
            
            # ===== 营业外支出 =====
            '营业外支出_违约金': 57,
            '营业外支出_罚款': 58,
        }
    
    def parse_filename(self, filename: str) -> Tuple[Optional[str], List[str]]:
        """
        解析文件名，提取银行名称和所有月份
        
        示例:
            "上海银行_1月_3月.xlsx" -> ("上海银行", ["1月", "2月", "3月"])
            "上海银行_1月.xlsx" -> ("上海银行", ["1月"])
        """
        name = Path(filename).stem
        
        pattern = r'^(.+?)_(\d+月)(?:_(\d+月))?$'
        match = re.match(pattern, name)
        
        if match:
            bank_name = match.group(1)
            start_month = match.group(2)
            end_month = match.group(3)
            
            if end_month:
                start_num = self._month_to_number(start_month)
                end_num = self._month_to_number(end_month)
                
                if start_num is not None and end_num is not None and start_num <= end_num:
                    month_list = self.MONTH_NAMES[start_num - 1:end_num]
                    return bank_name, month_list
                else:
                    return bank_name, [start_month]
            else:
                return bank_name, [start_month]
        
        if '_' in name:
            parts = name.split('_')
            if re.match(r'\d+月', parts[-1]):
                return parts[0], [parts[-1]]
        
        return name, ["未知"]
    
    def _month_to_number(self, month_str: str) -> Optional[int]:
        """将月份字符串转换为数字 1-12"""
        match = re.search(r'(\d+)', month_str)
        if match:
            num = int(match.group(1))
            if 1 <= num <= 12:
                return num
        return None
    
    def get_month_files(self, file_paths: List[Path]) -> List[Dict]:
        """生成汇总行计划"""
        plan = []
        for file_path in file_paths:
            bank_name, month_list = self.parse_filename(file_path.name)
            for month in month_list:
                plan.append({
                    "bank": bank_name,
                    "month": month,
                    "file": file_path
                })
        
        plan.sort(key=lambda x: (x["bank"], self._month_to_number(x["month"]) or 0))
        return plan
    
    def load_and_aggregate_file_for_month(self, file_path: Path, month: str, classification_config) -> Dict[int, Decimal]:
        """
        加载单个文件，只汇总指定月份的数据
        """
        transactions = self.data_loader.load_from_files([str(file_path)])
        
        if not transactions:
            return {}
        
        # 根据月份过滤
        month_num = self._month_to_number(month)
        if month_num is not None:
            filtered_transactions = []
            for trans in transactions:
                if hasattr(trans, 'date') and trans.date:
                    trans_month = trans.date.month
                    if trans_month == month_num:
                        filtered_transactions.append(trans)
            transactions = filtered_transactions
        
        if not transactions:
            return {}
        
        # 分类交易
        classified_transactions = []
        for trans in transactions:
            if isinstance(trans, ClassifiedTransaction):
                classified_transactions.append(trans)
            else:
                classified = self._classify_transaction(trans, classification_config)
                classified_transactions.append(classified)
        
        # 聚合数据
        report_data = self.aggregator.aggregate(classified_transactions)
        
        # 构建行数据字典
        row_data = self._build_row_data(report_data)
        
        return row_data
    
    def _classify_transaction(self, trans, classification_config) -> ClassifiedTransaction:
        """分类单笔交易 - 收入统一为"其他收入" """
        income_category = None
        expense_category = None
        
        contra = trans.contra_subject if hasattr(trans, 'contra_subject') else ""
        desc = trans.description if hasattr(trans, 'description') else ""
        
        if trans.is_income:
            # ===== 所有收入统一归入"其他收入" =====
            income_category = "其他收入"
        else:
            expense_category = classification_config.get_category_by_contra(contra, desc, is_income=False)
            if not expense_category:
                expense_category = "管理费用_其他"
        
        return ClassifiedTransaction(
            date=trans.date,
            voucher=trans.voucher,
            description=desc,
            debit=trans.debit,
            credit=trans.credit,
            contra_subject=contra,
            amount=trans.amount,
            is_income=trans.is_income,
            income_type=trans.income_type if hasattr(trans, 'income_type') else None,
            sheet_name=trans.sheet_name if hasattr(trans, 'sheet_name') else "",
            row_index=trans.row_index if hasattr(trans, 'row_index') else -1,
            quarter=trans.quarter if hasattr(trans, 'quarter') else None,
            quarter_confidence=trans.quarter_confidence if hasattr(trans, 'quarter_confidence') else 0.0,
            quarter_strategy=trans.quarter_strategy if hasattr(trans, 'quarter_strategy') else "",
            quarter_matched_rule=trans.quarter_matched_rule if hasattr(trans, 'quarter_matched_rule') else None,
            income_category=income_category,
            expense_category=expense_category,
            classification_confidence=0.8
        )
    
    def _build_row_data(self, report_data) -> Dict[int, Decimal]:
        """构建行数据字典 {列索引: 金额}"""
        row_data = {}
        
        # ===== 收入 - 统一归入"其他收入" =====
        # 所有收入都放入"其他收入"列（第17列）
        total_income = report_data.total_income
        if total_income > 0:
            row_data[17] = total_income
        
        # ===== 支出 - 按分类汇总 =====
        for category, amount in report_data.expense.items():
            if amount > 0:
                col = self.COL_MAPPING.get(category)
                if col:
                    row_data[col] = row_data.get(col, Decimal(0)) + amount
        
        return row_data
    
    def fill_summary_sheet(self, template_path: str, file_paths: List[Path], classification_config) -> Optional[str]:
        """
        填充汇总表 - 从第4行开始
        """
        from openpyxl import load_workbook
        
        if not template_path:
            raise ValueError("模板文件路径未设置")
        
        template_path = Path(template_path)
        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")
        
        # 生成汇总计划
        plan = self.get_month_files(file_paths)
        print(f"\n📊 汇总计划: 共 {len(plan)} 行")
        for item in plan:
            print(f"  {item['bank']} - {item['month']} <- {item['file'].name}")
        
        wb = load_workbook(template_path)
        
        # 找到汇总表
        summary_sheet_name = None
        for sheet_name in wb.sheetnames:
            if '汇总表' in sheet_name:
                summary_sheet_name = sheet_name
                break
        
        if summary_sheet_name is None:
            # 如果模板中有"汇总表_临时"或其他名称，尝试创建
            if '汇总表_临时' in wb.sheetnames:
                summary_sheet_name = '汇总表_临时'
            else:
                raise ValueError("未找到'汇总表'工作表")
        
        ws = wb[summary_sheet_name]
        
        # 从第4行开始填入数据
        start_row = 4
        
        # 清空第4行及以下
        max_row = ws.max_row
        if max_row >= start_row:
            for row in range(start_row, max_row + 1):
                for col in range(1, ws.max_column + 1):
                    ws.cell(row=row, column=col, value=None)
        
        # 为每个汇总项创建一行
        for idx, item in enumerate(plan):
            current_row = start_row + idx
            
            # 行号列（A列）：银行名称
            ws.cell(row=current_row, column=1, value=item["bank"])
            
            # 交易时间列（B列）：月份
            ws.cell(row=current_row, column=2, value=item["month"])
            
            # 加载并汇总该文件对应月份的数据
            print(f"  📊 处理: {item['bank']} - {item['month']}")
            row_data = self.load_and_aggregate_file_for_month(
                item["file"], 
                item["month"], 
                classification_config
            )
            
            # 填入数据
            for col, amount in row_data.items():
                if amount != 0:
                    ws.cell(row=current_row, column=col, value=float(amount))
            
            # 打印收入汇总（调试用）
            total_income = row_data.get(17, Decimal(0))
            if total_income > 0:
                print(f"    ✅ {item['bank']} - {item['month']} 收入合计: {total_income:.2f} (已归入其他收入)")
        
        # 保存
        wb.save(str(template_path))
        print(f"✅ 汇总表已更新: {template_path}")
        
        return str(template_path)