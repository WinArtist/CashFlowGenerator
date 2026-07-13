# src/services/reporter.py - 修复版（删除季度引用）
"""报表生成服务"""

from decimal import Decimal
from typing import List, Dict, Any
import pandas as pd
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.report_data import ReportData
from CashFlowGenerator.config import Config


class ReportGenerator:
    """报表生成器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.decimal_places = config.data.decimal_places
    
    def generate(self, report_data: ReportData, output_path: str) -> str:
        """生成报表文件"""
        rows = self._build_rows(report_data)
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df_main = pd.DataFrame(rows)
            df_main.to_excel(writer, sheet_name='年度财务收支表', index=False, header=False)
            self._write_summary_sheet(writer, report_data)
            self._write_detail_sheet(writer, report_data)
        
        return output_path
    
    def _build_rows(self, report_data: ReportData) -> List[List]:
        """构建报表行"""
        rows = []
        
        rows.append([f'{self.config.data.report_year}年资金收支报表', '', '', '', '', '', '', '', '', ''])
        rows.append(['', '', '', '', '', '', '', '', '', ''])
        rows.append(['项目', '合计', '', '', '', '', '', '占比', '', ''])
        rows.append(['期初数：', '0', '0', '0', '', '', '', '', '', ''])
        
        # 收入部分
        rows.append(['1、主营收入：', f"{report_data.total_income:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        for category in ['产品收入', '服务收入', '其他收入']:
            amount = report_data.income.get(category, Decimal(0))
            rows.append([category, f"{amount:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        
        rows.append(['', '', '', '', '', '', '', '', '', ''])
        rows.append(['2、股东投入：', '0', '0', '0', '', '', '', '', '', ''])
        rows.append(['本期收入合计：', f"{report_data.total_income:.{self.decimal_places}f}", 
                    f"{report_data.total_income:.{self.decimal_places}f}", '0', '', '', '', '', '', ''])
        rows.append(['本期支出合计：', f"{report_data.total_expense:.{self.decimal_places}f}", 
                    f"{report_data.total_expense:.{self.decimal_places}f}", '0', '', '', '', '', '', ''])
        
        # 支出部分
        main_business = (report_data.expense.get('商品采购', Decimal(0)) +
                        report_data.expense.get('运费', Decimal(0)) +
                        report_data.expense.get('服务费', Decimal(0)) +
                        report_data.expense.get('返点佣金', Decimal(0)))
        rows.append(['1、主营业务支出', f"{main_business:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        
        for category in ['商品采购', '运费', '服务费', '返点佣金']:
            amount = report_data.expense.get(category, Decimal(0))
            rows.append([category, f"{amount:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        
        management_categories = ['管理_办公费', '管理_租金物业', '管理_人员薪资', 
                                 '管理_社保公积金', '管理_员工福利', '管理_通讯费', '管理_其他']
        management_total = sum(report_data.expense.get(c, Decimal(0)) for c in management_categories)
        
        rows.append(['2、研发费用', '0', '', '', '', '', '', '', '', ''])
        
        sales_total = report_data.get_expense_by_prefix('销售_')
        rows.append(['3、销售费用', f"{sales_total:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        
        rows.append(['4、管理费用', f"{management_total:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        
        for category in ['管理_人员薪资', '管理_社保公积金', '管理_员工福利', 
                         '管理_租金物业', '管理_办公费', '管理_通讯费']:
            amount = report_data.expense.get(category, Decimal(0))
            if amount > 0:
                display_name = category.replace('管理_', '')
                rows.append([display_name, f"{amount:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        
        financial_total = (report_data.expense.get('财务_手续费', Decimal(0)) +
                          abs(report_data.expense.get('财务_结息', Decimal(0))))
        rows.append(['5、财务费用', f"{financial_total:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        rows.append(['手续费', f"{report_data.expense.get('财务_手续费', Decimal(0)):.{self.decimal_places}f}", 
                    '', '', '', '', '', '', '', ''])
        
        tax_total = report_data.get_expense_by_prefix('税金_')
        rows.append(['6、固定资产', '0', '', '', '', '', '', '', '', ''])
        rows.append(['7、预付/暂支款', '0', '', '', '', '', '', '', '', ''])
        rows.append(['8、营业外支出', '0', '', '', '', '', '', '', '', ''])
        rows.append(['9、税金支出', f"{tax_total:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        rows.append(['代扣代缴个税', f"{report_data.expense.get('税金_个税', Decimal(0)):.{self.decimal_places}f}", 
                    '', '', '', '', '', '', '', ''])
        rows.append(['10、集团划拨往来', '0', '0', '0', '', '', '', '', '', ''])
        
        # 汇总
        rows.append(['本月资金净流入', f"{report_data.net_flow:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        rows.append(['本月资金余额', f"{report_data.net_flow:.{self.decimal_places}f}", '', '', '', '', '', '', '', ''])
        
        return rows
    
    def _write_summary_sheet(self, writer: pd.ExcelWriter, report_data: ReportData):
        """写入汇总表"""
        summary = []
        summary.append(['现金流量汇总表', ''])
        summary.append(['生成时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        summary.append(['', ''])
        summary.append(['收入类别', '合计(元)'])
        
        for category in ['产品收入', '服务收入', '其他收入']:
            amount = report_data.income.get(category, Decimal(0))
            summary.append([category, f"{amount:.2f}"])
        
        summary.append(['收入合计', f"{report_data.total_income:.2f}"])
        summary.append(['', ''])
        summary.append(['支出类别', '合计(元)'])
        
        expense_order = ['商品采购', '运费', '服务费', '管理_人员薪资', '管理_社保公积金', 
                         '管理_员工福利', '管理_租金物业', '销售_招待费', '财务_手续费', '税金_个税']
        for category in expense_order:
            amount = report_data.expense.get(category, Decimal(0))
            if amount > 0:
                display_name = category.replace('管理_', '').replace('销售_', '').replace('税金_', '')
                summary.append([display_name, f"{amount:.2f}"])
        
        summary.append(['支出合计', f"{report_data.total_expense:.2f}"])
        summary.append(['', ''])
        summary.append(['净现金流', f"{report_data.net_flow:.2f}"])
        
        df_summary = pd.DataFrame(summary)
        df_summary.to_excel(writer, sheet_name='数据汇总', index=False, header=False)
    
    def _write_detail_sheet(self, writer: pd.ExcelWriter, report_data: ReportData):
        """写入明细表"""
        details = []
        details.append(['分类明细', '金额(元)'])
        
        details.append(['【收入类】', ''])
        for category, amount in sorted(report_data.income.items(), key=lambda x: -x[1]):
            if amount > 0:
                details.append([category, f"{amount:.2f}"])
        
        details.append(['', ''])
        details.append(['【支出类】', ''])
        for category, amount in sorted(report_data.expense.items(), key=lambda x: -x[1]):
            if amount > 0:
                details.append([category, f"{amount:.2f}"])
        
        df_detail = pd.DataFrame(details)
        df_detail.to_excel(writer, sheet_name='分类明细', index=False, header=False)