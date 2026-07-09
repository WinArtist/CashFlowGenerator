# src/main.py
"""现金流量报表生成器 - 整合版主入口
流程：检查数据 → 生成模板 → 填入数据
"""

from decimal import Decimal
import shutil
import sys
from pathlib import Path
from datetime import datetime
import tempfile
from typing import Optional, List
import argparse

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from config import Config, Environment
from services.data_loader import DataLoader
from services.quarter_mapper import QuarterMapper, QuarterMapperBuilder
from services.aggregator import DataAggregator
from services.validator import DataValidator
from services.reporter import ReportGenerator
from services.direct_sheet_filler import JianhangQ2Filler
from services.create_blank_template import create_template_from_detail
from services.summary_service import SummaryService
from models.transaction import ClassifiedTransaction


class CashFlowReportGenerator:
    def __init__(self, environment: Environment = Environment.DEVELOPMENT):
        self.config = Config.get_instance(environment)
        self.config.reload_classification()

        print("=" * 60)
        print("🔧 CashFlowReportGenerator 初始化")
        print("=" * 60)

        expense_rules = self.config.data.classification.expense_rules
        income_rules = self.config.data.classification.income_rules
        print(f"📊 当前配置中的收入规则数量: {len(income_rules)}")
        for i, rule in enumerate(income_rules):
            keywords = []
            for cr in rule.contra_rules:
                keywords.extend(cr.keywords)
            print(f"  {i+1}. {rule.category}: {keywords}")
        print(f"📊 当前配置中的支出规则数量: {len(expense_rules)}")
        for i, rule in enumerate(expense_rules):
            keywords = []
            for cr in rule.contra_rules:
                keywords.extend(cr.keywords)
            print(f"  {i+1}. {rule.category}: {keywords}")

        print("=" * 60)

        self.project_root = PROJECT_ROOT
        self.quarter_mapper = self._build_quarter_mapper()
        self.data_loader = DataLoader(self.config, self.quarter_mapper)
        self.aggregator = DataAggregator(self.config)
        self.validator = DataValidator(
            threshold=self.config.data.validation_threshold
        )
        self.reporter = ReportGenerator(self.config)
        self.filler = JianhangQ2Filler(self.config)
        self.summary_service = SummaryService(self.config)

        # 状态记录
        self.transactions = []
        self.template_path = None
        self.output_path = None

        # 额外参数
        self.bank_name = None
        self.period_value = None
        self.sheet_name = None
        self.output_filename = None
        self._output_path = None
    
    def set_output_path(self, output_path: Path):
        """设置输出路径（由GUI调用）"""
        self._output_path = output_path
    
    def _build_quarter_mapper(self) -> QuarterMapper:
        """构建季度映射器"""
        builder = QuarterMapperBuilder()
        quarter_config = self.config.data.quarter_mapping
        
        if quarter_config.strategy.value == "by_date":
            builder.use_date_based()
        elif quarter_config.strategy.value == "by_month_mapping":
            builder.use_custom_month_mapping(quarter_config.month_mapping)
        
        for rule in quarter_config.month_rules:
            builder.add_month_rule(rule.month, rule.target_quarter, rule.description)
        
        for rule in quarter_config.voucher_rules:
            builder.add_voucher_rule(rule.prefix, rule.target_quarter, rule.description)
        
        for rule in quarter_config.sheet_rules:
            builder.add_sheet_rule(rule.keyword, rule.target_quarter, rule.description)
        
        builder.set_default_quarter(quarter_config.default_quarter)
        
        if quarter_config.fuzzy_match:
            builder.enable_fuzzy_match(True)
        
        return builder.build()
    
    def get_input_dir(self) -> Path:
        """获取输入目录"""
        return self.project_root / self.config.file.input_dir
    
    def get_output_dir(self) -> Path:
        """获取输出目录"""
        if self._output_path:
            return self._output_path.parent
        return self.project_root / self.config.file.output_dir
    
    def get_template_path(self) -> Path:
        """获取模板路径 - 支持打包环境从内存读取"""
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                meipass = Path(sys._MEIPASS)
                template_path = meipass / 'templates' / self.config.file.template_filename
                if template_path.exists():
                    print(f"✅ 从打包资源加载模板: {template_path}")
                    return template_path
        
            exe_dir = Path(sys.executable).parent
            template_path = exe_dir / 'templates' / self.config.file.template_filename
            if template_path.exists():
                print(f"✅ 从 exe 目录加载模板: {template_path}")
                return template_path
        
            temp_dir = Path(tempfile.gettempdir()) / 'cashflow_template'
            template_path = temp_dir / self.config.file.template_filename
            if template_path.exists():
                print(f"✅ 从临时目录加载模板: {template_path}")
                return template_path
        
            if hasattr(sys, '_MEIPASS'):
                meipass = Path(sys._MEIPASS)
                source = meipass / 'templates' / self.config.file.template_filename
                if source.exists():
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    dest = temp_dir / self.config.file.template_filename
                    shutil.copy2(source, dest)
                    print(f"✅ 模板已复制到临时目录: {dest}")
                    return dest
    
        template_path = self.project_root / self.config.file.template_dir / self.config.file.template_filename
        if template_path.exists():
            print(f"✅ 从项目目录加载模板: {template_path}")
            return template_path
    
        print(f"❌ 模板文件不存在: {template_path}")
        return template_path
    
    def scan_input_files(self) -> List[Path]:
        """扫描input目录下的所有Excel文件"""
        input_dir = self.get_input_dir()
        if not input_dir.exists():
            return []
        
        excel_files = []
        for ext in self.config.file.supported_extensions:
            excel_files.extend(input_dir.glob(f"*{ext}"))
        
        excel_files = [f for f in excel_files if not f.name.startswith('~$')]
        return sorted(excel_files, key=lambda x: x.stat().st_mtime, reverse=True)
    
    def display_files_table(self, files: list) -> None:
        """显示文件列表"""
        if not files:
            print("未找到任何Excel文件")
            return
        
        print("\n" + "=" * 80)
        print(f"{'序号':<6} {'文件名':<50} {'大小':<12}")
        print("=" * 80)
        
        for idx, file_path in enumerate(files, 1):
            size_kb = file_path.stat().st_size / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            filename = file_path.name
            if len(filename) > 48:
                filename = filename[:45] + "..."
            print(f"{idx:<6} {filename:<50} {size_str:<12}")
        
        print("=" * 80)
        print(f"共找到 {len(files)} 个文件")
    
    def select_input_file(self) -> Optional[Path]:
        """选择输入文件"""
        input_files = self.scan_input_files()
        
        if not input_files:
            print(f"\n❌ input目录下没有找到Excel文件")
            print(f"   请将明细账文件放入: {self.get_input_dir()}")
            return None
        
        self.display_files_table(input_files)
        
        if len(input_files) == 1:
            selected = input_files[0]
            print(f"\n自动选择: {selected.name}")
            return selected
        
        while True:
            try:
                choice = input(f"\n请选择文件 (1-{len(input_files)}): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(input_files):
                    return input_files[idx]
                print(f"请输入 1-{len(input_files)} 之间的数字")
            except ValueError:
                print("请输入有效数字")
    
    def load_transactions(self, file_path: Path) -> List:
        """加载交易数据"""
        print(f"\n📊 加载交易数据...")
        transactions = self.data_loader.load_from_files([str(file_path)])
        print(f"✅ 共加载 {len(transactions)} 笔交易")
        return transactions
    
    def validate_transactions(self, transactions: List) -> bool:
        """校验交易数据，返回是否有效"""
        if not transactions:
            print("❌ 没有找到有效的交易数据")
            return False
        
        result = self.validator.validate_transactions(transactions)
        
        if result.errors:
            print(f"❌ 校验错误:")
            for err in result.errors:
                print(f"   - {err}")
            return False
        
        if result.warnings:
            print(f"⚠️ 校验警告:")
            for warn in result.warnings:
                print(f"   - {warn}")
        
        return True
    
    def generate_template(self, detail_path: Path, bank_name: str, period: str, 
                      output_filename: str, sheet_name: str) -> Optional[str]:
        """根据明细账生成模板"""
        print(f"\n📁 生成模板...")

        if not bank_name:
            raise ValueError("银行名称未设置")
        if not period:
            raise ValueError("期间未设置")
        if not output_filename:
            raise ValueError("输出文件名未设置")
        if not sheet_name:
            raise ValueError("工作表名称未设置")

        template_path = self.get_template_path()
    
        if not template_path or not template_path.exists():
            print(f"❌ 模板文件不存在: {template_path}")
            print(f"   请确保 templates/现金流原始表.xlsx 文件存在")
            return None
    
        print(f"✅ 使用模板: {template_path}")

        if self._output_path:
            output_dir = str(self._output_path.parent)
            filename = self._output_path.name
            print(f"📂 使用用户指定输出路径: {self._output_path}")
        else:
            output_dir = str(self.get_output_dir())
            filename = output_filename
            print(f"📂 使用默认输出目录: {output_dir}")

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        result = create_template_from_detail(
            detail_path=str(detail_path),
            template_path=str(template_path),
            output_dir=output_dir,
            bank_name=bank_name,
            period=period,
            output_filename=filename,
            sheet_name=sheet_name
        )

        if result:
            print(f"✅ 模板已生成: {result}")
            self.template_path = result

        return result
 
    def fill_data(self, template_path: str, transactions: List, quarter: str, sheet_name: str, opening_balance: Optional[Decimal] = None) -> Optional[str]:
        """将数据填入模板"""
        if not template_path:
            raise ValueError("模板文件路径未设置")
        if not quarter:
            raise ValueError("季度未设置")
        if not sheet_name:
            raise ValueError("工作表名称未设置")
    
        print(f"\n📝 填入数据到工作表: {sheet_name}")
    
        classified_transactions = []
        for trans in transactions:
            if isinstance(trans, ClassifiedTransaction):
                classified_transactions.append(trans)
            else:
                classified = self._classify_transaction(trans)
                classified_transactions.append(classified)
    
        report_data = self.aggregator.aggregate(classified_transactions)
    
        print(f"  收入总计: ¥{report_data.total_income:,.2f}")
        print(f"  支出总计: ¥{report_data.total_expense:,.2f}")
        print(f"  净现金流: ¥{report_data.net_flow:,.2f}")
    
        if opening_balance is not None:
            print(f"  期初余额: ¥{opening_balance:,.2f}")
    
        report_data._transactions = classified_transactions
    
        result = self.filler.fill_quarter_data(
            template_path=template_path,
            report_data=report_data,
            quarter=quarter,
            source_file=Path(template_path).name,
            sheet_name=sheet_name,
            opening_balance=opening_balance
        )
    
        if result:
            print(f"✅ 数据已填入: {result}")
            self.output_path = result
    
        return result
    
    def _classify_transaction(self, trans) -> ClassifiedTransaction:
        """分类单笔交易"""
        income_category = None
        expense_category = None
        
        if trans.is_income:
            income_category = self._classify_income(trans)
        else:
            expense_category = self._classify_expense(trans)
        
        return ClassifiedTransaction(
            date=trans.date,
            voucher=trans.voucher,
            description=trans.description,
            debit=trans.debit,
            credit=trans.credit,
            contra_subject=trans.contra_subject if hasattr(trans, 'contra_subject') else "",
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
    
    def _classify_income(self, trans) -> str:
        """分类收入 - 复用 aggregator 的逻辑"""
        return self.aggregator._classify_income(trans)
    
    def _classify_expense(self, trans) -> str:
        """分类支出 - 复用 aggregator 的逻辑"""
        return self.aggregator._classify_expense(trans)
    
    def generate_report(self, transactions: List, output_path: Optional[str] = None) -> Optional[str]:
        """生成报表"""
        print(f"\n📊 生成报表...")
        
        report_data = self.aggregator.aggregate(transactions)
        
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(self.get_output_dir() / f"现金流报表_{timestamp}.xlsx")
        
        result = self.reporter.generate(report_data, output_path)
        print(f"✅ 报表已生成: {result}")
        return result
    
    def print_summary(self, transactions: List):
        """打印汇总信息"""
        total_income = sum(t.amount for t in transactions if t.is_income)
        total_expense = sum(t.amount for t in transactions if not t.is_income)
        
        print("\n" + "=" * 60)
        print("数据汇总:")
        print(f"  总交易笔数: {len(transactions)}")
        print(f"  收入笔数: {len([t for t in transactions if t.is_income])}")
        print(f"  支出笔数: {len([t for t in transactions if not t.is_income])}")
        print(f"  总收入: ¥{total_income:,.2f}")
        print(f"  总支出: ¥{total_expense:,.2f}")
        print(f"  净现金流: ¥{total_income - total_expense:,.2f}")
        print("=" * 60)
        
        print("\n前5笔交易示例:")
        print("-" * 80)
        print(f"{'序号':<6} {'日期':<12} {'摘要':<30} {'金额':<15} {'类型':<10}")
        print("-" * 80)
        for i, t in enumerate(transactions[:5]):
            date_str = t.date.strftime('%Y-%m-%d') if hasattr(t, 'date') and t.date else ''
            desc = t.description[:28] if hasattr(t, 'description') else ''
            amount_str = f"¥{t.amount:,.2f}" if hasattr(t, 'amount') else ''
            type_str = "收入" if t.is_income else "支出"
            print(f"{i+1:<6} {date_str:<12} {desc:<30} {amount_str:<15} {type_str:<10}")
        print("-" * 80)
    
    def run_full_flow(self, input_file: Path, quarter: str) -> bool:
        """执行完整流程：检查数据 → 生成模板 → 填入数据"""
        print("\n" + "=" * 60)
        print("    开始执行完整流程")
        print(f"    输入文件: {input_file.name}")
        print(f"    目标季度: {quarter}")
        print(f"    输出路径: {self._output_path}")
        print("=" * 60)

        try:
            if not self.bank_name:
                raise ValueError("银行名称未设置 (bank_name)")
            if not self.period_value:
                raise ValueError("期间值未设置 (period_value)")
            if not self.sheet_name:
                raise ValueError("工作表名称未设置 (sheet_name)")
            if not self.output_filename:
                raise ValueError("输出文件名未设置 (output_filename)")

            print(f"  银行: {self.bank_name}")
            print(f"  期间显示: {self.period_value}")
            print(f"  工作表名称: {self.sheet_name}")
            print(f"  输出文件名: {self.output_filename}")

            # 步骤1: 加载数据
            print("\n📊 步骤1: 加载数据...")
            all_transactions = self.data_loader.load_from_files([str(input_file)])
            opening_balance = self._extract_opening_balance_from_file(input_file)
            
            if opening_balance is None:
                opening_balance = self._find_opening_balance(all_transactions)
            
            if opening_balance is None:
                print("  ⚠️ 未找到期初余额，使用 0")
                opening_balance = Decimal(0)

            transactions = all_transactions
        
            if not self.validate_transactions(transactions):
                return False
            self.transactions = transactions
            self.print_summary(transactions)

            # 步骤2: 生成模板
            print("\n📁 步骤2: 生成模板...")
            template_path = self.generate_template(
                input_file, 
                self.bank_name, 
                self.period_value, 
                self.output_filename,
                self.sheet_name
            )
            if not template_path:
                print("❌ 模板生成失败")
                return False
            print(f"✅ 模板已生成: {template_path}")

            # 步骤3: 填入数据
            print("\n📝 步骤3: 填入数据...")
            filled_path = self.fill_data(template_path, transactions, quarter, self.sheet_name, opening_balance)
            if not filled_path:
                print("❌ 数据填入失败")
                return False
            print(f"✅ 数据已填入: {filled_path}")

            print("\n" + "=" * 60)
            print("✅ 全部完成!")
            print(f"📁 模板文件: {template_path}")
            print(f"📁 填入文件: {filled_path}")
            if opening_balance is not None:
                print(f"📊 期初余额: ¥{opening_balance:,.2f}")
            print("=" * 60)

            return True
    
        except Exception as e:
            import traceback
            print(f"❌ run_full_flow 异常: {e}")
            print(traceback.format_exc())
            return False

    def _extract_opening_balance_from_file(self, file_path: Path) -> Optional[Decimal]:
        """直接从明细账文件提取期初余额（第6行I列）"""
        try:
            import pandas as pd
            df = pd.read_excel(str(file_path), header=None, dtype=str)
            
            if len(df) > 5 and len(df.iloc[5]) > 8:
                val = df.iloc[5, 8]
                if pd.notna(val):
                    clean_val = str(val).replace(',', '').replace(' ', '').strip()
                    result = Decimal(clean_val)
                    print(f"  📊 期初余额（第6行I列）: {result:.2f}")
                    return result
            
            for row_idx in range(min(10, len(df))):
                row = df.iloc[row_idx]
                for col_idx in range(min(10, len(row))):
                    cell_val = str(row.iloc[col_idx]) if pd.notna(row.iloc[col_idx]) else ''
                    if '期初余额' in cell_val:
                        if len(row) > 8:
                            balance_val = row.iloc[8]
                            if pd.notna(balance_val):
                                clean_val = str(balance_val).replace(',', '').replace(' ', '').strip()
                                result = Decimal(clean_val)
                                print(f"  📊 期初余额（查找'期初余额'）: {result:.2f}")
                                return result
            
            return None
        except Exception as e:
            print(f"  ❌ 提取期初余额失败: {e}")
            return None

    def _find_opening_balance(self, transactions: List) -> Optional[Decimal]:
        """从交易列表中查找期初余额"""
        for trans in transactions:
            if hasattr(trans, 'voucher') and trans.voucher:
                if '期初余额' in trans.voucher:
                    return trans.amount
            if hasattr(trans, 'description') and trans.description:
                if '期初余额' in trans.description:
                    return trans.amount
        return None

    def run_summary(self, file_paths: List[Path], output_path: Optional[Path] = None) -> bool:
        """执行汇总功能：将多个明细账文件汇总到汇总表"""
        print("\n" + "=" * 60)
        print("    开始执行汇总")
        print(f"    文件数量: {len(file_paths)}")
        print("=" * 60)
    
        if not file_paths:
            print("❌ 没有文件需要汇总")
            return False
    
        try:
            if output_path is None:
                output_dir = file_paths[0].parent
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = output_dir / f"汇总表_{timestamp}.xlsx"
            else:
                output_path = Path(output_path)
                output_dir = output_path.parent
        
            output_dir.mkdir(parents=True, exist_ok=True)
        
            template_path = self.get_template_path()
            if not template_path or not template_path.exists():
                print(f"❌ 模板文件不存在: {template_path}")
                return False
        
            # ===== 关键修改：只在文件不存在时复制模板 =====
            if not output_path.exists():
                shutil.copy2(template_path, output_path)
                print(f"📄 已创建新文件: {output_path}")
            else:
                print(f"📄 使用已有文件: {output_path}")
        
            # ===== 调用汇总服务 =====
            result = self.summary_service.fill_summary_sheet(
                str(output_path),
                file_paths,
                self.config.data.classification
            )
        
            if result:
                print(f"\n✅ 汇总完成!")
                print(f"📁 输出文件: {result}")
                self.output_path = result
                return True
            else:
                print("❌ 汇总失败")
                return False
            
        except Exception as e:
            import traceback
            print(f"❌ 汇总异常: {e}")
            print(traceback.format_exc())
            return False 


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='现金流量报表生成器')
    parser.add_argument('--mode', '-m', 
                        choices=['full', 'template', 'fill', 'report', 'summary'],
                        default='full', 
                        help='运行模式: full(完整流程), template(仅生成模板), fill(仅填入数据), report(仅生成报表), summary(汇总模式)')
    parser.add_argument('--input', '-i', 
                        help='输入文件路径（指定则跳过文件选择）')
    parser.add_argument('--template', '-t', 
                        help='模板文件路径（fill模式使用）')
    parser.add_argument('--output', '-o', 
                        help='输出文件路径')
    parser.add_argument('--quarter', '-q', 
                        default='Q2', 
                        help='目标季度 (默认: Q2)')
    parser.add_argument('--env', 
                        choices=['dev', 'test', 'prod'],
                        default='dev', 
                        help='运行环境')
    
    args = parser.parse_args()
    
    env_map = {
        'dev': Environment.DEVELOPMENT,
        'test': Environment.TESTING,
        'prod': Environment.PRODUCTION
    }
    env = env_map.get(args.env, Environment.DEVELOPMENT)
    
    generator = CashFlowReportGenerator(env)
    
    print("=" * 60)
    print("    现金流量报表生成器")
    print(f"    环境: {env.value}")
    print(f"    模式: {args.mode}")
    print(f"    项目根目录: {PROJECT_ROOT}")
    print("=" * 60)
    
    input_dir = generator.get_input_dir()
    if not input_dir.exists():
        input_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n📁 已创建 input 目录: {input_dir}")
        print(f"   请将明细账文件放入该目录")
        return 1
    
    output_dir = generator.get_output_dir()
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.mode == 'summary':
        # 汇总模式
        print("\n" + "=" * 60)
        print("    模式: 汇总模式")
        print("=" * 60)
        
        if args.input:
            input_files = [Path(args.input)]
        else:
            input_files = generator.scan_input_files()
            if not input_files:
                print("❌ 没有找到Excel文件")
                return 1
        
        result = generator.run_summary(input_files, Path(args.output) if args.output else None)
        return 0 if result else 1
    
    if args.input:
        input_file = Path(args.input)
        if not input_file.exists():
            print(f"❌ 指定的输入文件不存在: {input_file}")
            return 1
        print(f"\n📁 使用指定的文件: {input_file}")
    else:
        input_file = generator.select_input_file()
        if input_file is None:
            return 1
    
    if args.mode == 'template':
        print("\n" + "=" * 60)
        print("    模式: 仅生成模板")
        print("=" * 60)
        
        result = generator.generate_template(input_file)
        if result:
            print(f"\n✅ 模板生成成功: {result}")
        return 0
    
    if args.mode == 'fill':
        print("\n" + "=" * 60)
        print("    模式: 仅填入数据")
        print("=" * 60)
        
        transactions = generator.load_transactions(input_file)
        if not generator.validate_transactions(transactions):
            return 1
        
        template_path = args.template or generator.template_path or str(generator.get_template_path())
        if not Path(template_path).exists():
            print(f"❌ 模板文件不存在: {template_path}")
            print(f"   请先运行模板生成模式，或使用 -t 指定模板文件")
            return 1
        
        result = generator.fill_data(template_path, transactions, args.quarter)
        if result:
            print(f"\n✅ 数据填入成功: {result}")
        return 0
    
    if args.mode == 'report':
        print("\n" + "=" * 60)
        print("    模式: 仅生成报表")
        print("=" * 60)
        
        transactions = generator.load_transactions(input_file)
        if not generator.validate_transactions(transactions):
            return 1
        
        result = generator.generate_report(transactions, args.output)
        if result:
            print(f"\n✅ 报表生成成功: {result}")
        return 0
    
    # 完整流程 (默认)
    success = generator.run_full_flow(input_file, args.quarter)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())