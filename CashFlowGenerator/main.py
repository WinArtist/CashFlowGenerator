# src/main.py - 完整修复版（删除所有季度相关引用）
"""现金流量报表生成器 - 整合版主入口"""

from decimal import Decimal
import shutil
import sys
from pathlib import Path
from datetime import datetime
import tempfile
from typing import Optional, List
import argparse

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from CashFlowGenerator.config import Config, Environment
from services.data_loader import DataLoader
from services.aggregator import DataAggregator
from services.validator import DataValidator
from services.reporter import ReportGenerator
from services.direct_sheet_filler import SheetFiller
from services.create_blank_template import create_template_from_detail
from services.summary_service import SummaryService
from models.transaction import ClassifiedTransaction


class CashFlowReportGenerator:
    """现金流量报表生成器"""
    
    def __init__(self, environment: Environment = Environment.DEVELOPMENT):
        self.config = Config.get_instance(environment)
        self.config.reload_classification()

        print("=" * 60)
        print("🔧 CashFlowReportGenerator 初始化")
        print("=" * 60)

        expense_rules = self.config.data.classification.expense_rules
        income_rules = self.config.data.classification.income_rules
        print(f"📊 收入规则: {len(income_rules)} 条")
        print(f"📊 支出规则: {len(expense_rules)} 条")
        print("=" * 60)

        self.project_root = PROJECT_ROOT
        self.data_loader = DataLoader(self.config)
        self.aggregator = DataAggregator(self.config)
        self.validator = DataValidator(threshold=self.config.data.validation_threshold)
        self.reporter = ReportGenerator(self.config)
        self.filler = SheetFiller(self.config)
        self.summary_service = SummaryService(self.config)

        self.transactions = []
        self.template_path = None
        self.output_path = None

        self.bank_name = None
        self.period_value = None
        self.sheet_name = None
        self.output_filename = None
        self._output_path = None
    
    def set_output_path(self, output_path: Path):
        """设置输出路径"""
        self._output_path = output_path
    
    def get_input_dir(self) -> Path:
        return self.project_root / self.config.file.input_dir
    
    def get_output_dir(self) -> Path:
        if self._output_path:
            return self._output_path.parent
        return self.project_root / self.config.file.output_dir
    
    def get_template_path(self) -> Path:
        """获取模板路径 - 支持打包环境"""
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                meipass = Path(sys._MEIPASS)
                template_path = meipass / 'templates' / self.config.file.template_filename
                if template_path.exists():
                    return template_path
        
            exe_dir = Path(sys.executable).parent
            template_path = exe_dir / 'templates' / self.config.file.template_filename
            if template_path.exists():
                return template_path
        
            temp_dir = Path(tempfile.gettempdir()) / 'cashflow_template'
            template_path = temp_dir / self.config.file.template_filename
            if template_path.exists():
                return template_path
        
            if hasattr(sys, '_MEIPASS'):
                meipass = Path(sys._MEIPASS)
                source = meipass / 'templates' / self.config.file.template_filename
                if source.exists():
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    dest = temp_dir / self.config.file.template_filename
                    shutil.copy2(source, dest)
                    return dest
    
        template_path = self.project_root / self.config.file.template_dir / self.config.file.template_filename
        if template_path.exists():
            return template_path
    
        print(f"❌ 模板文件不存在: {template_path}")
        return template_path
    
    def load_transactions(self, file_path: Path) -> List:
        """加载交易数据"""
        print(f"\n📊 加载交易数据...")
        transactions = self.data_loader.load_from_files([str(file_path)])
        print(f"✅ 共加载 {len(transactions)} 笔交易")
        return transactions
    
    def validate_transactions(self, transactions: List) -> bool:
        """校验交易数据"""
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
        """生成模板"""
        print(f"\n📁 生成模板...")

        if not all([bank_name, period, output_filename, sheet_name]):
            raise ValueError("必要参数缺失")

        template_path = self.get_template_path()
        if not template_path or not template_path.exists():
            print(f"❌ 模板文件不存在: {template_path}")
            return None

        if self._output_path:
            output_dir = str(self._output_path.parent)
            filename = self._output_path.name
        else:
            output_dir = str(self.get_output_dir())
            filename = output_filename

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
 
    def fill_data(self, template_path: str, transactions: List, sheet_name: str, 
                  opening_balance: Optional[Decimal] = None) -> Optional[str]:
        """填入数据"""
        if not template_path:
            raise ValueError("模板文件路径未设置")
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
    
        result = self.filler.fill_sheet(
            template_path=template_path,
            report_data=report_data,
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
            income_category = self.config.data.classification.default_income_category
        else:
            expense_category = self._classify_expense(trans)
        
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
            income_category=income_category,
            expense_category=expense_category,
            classification_confidence=0.8
        )
    
    def _classify_expense(self, trans) -> str:
        """分类支出"""
        contra = getattr(trans, 'contra_subject', "") or ""
        desc = trans.description or ""
        category = self.config.data.classification.get_category_by_contra(contra, desc, is_income=False)
        return category if category else self.config.data.classification.default_expense_category
    
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
    
    def get_opening_balance(self, file_path: Path) -> Optional[Decimal]:
        """获取期初余额"""
        return self.data_loader.get_opening_balance(str(file_path))
    
    def run_full_flow(self, input_file: Path) -> bool:
        """执行完整流程"""
        print("\n" + "=" * 60)
        print("    开始执行完整流程")
        print(f"    输入文件: {input_file.name}")
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
            print(f"  期间: {self.period_value}")
            print(f"  工作表: {self.sheet_name}")

            print("\n📊 步骤1: 加载数据...")
            all_transactions = self.data_loader.load_from_files([str(input_file)])
            opening_balance = self.get_opening_balance(input_file)
        
            if opening_balance is None:
                opening_balance = self._find_opening_balance(all_transactions)
        
            if opening_balance is None:
                print("  ⚠️ 未找到期初余额，使用 0")
                opening_balance = Decimal(0)

            transactions = all_transactions
        
            if not transactions:
                print("  ⚠️ 没有找到交易数据，将创建空Sheet")
        
            self.transactions = transactions
            self.print_summary(transactions)

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

            if transactions:
                print("\n📝 步骤3: 填入数据...")
                filled_path = self.fill_data(template_path, transactions, self.sheet_name, opening_balance)
                if not filled_path:
                    print("❌ 数据填入失败")
                    return False
            else:
                print("  ⚠️ 无交易数据，保留空Sheet")
                filled_path = template_path

            print("\n" + "=" * 60)
            print("✅ 全部完成!")
            print(f"📁 输出文件: {filled_path}")
            if opening_balance is not None:
                print(f"📊 期初余额: ¥{opening_balance:,.2f}")
            print("=" * 60)

            return True
    
        except Exception as e:
            import traceback
            print(f"❌ run_full_flow 异常: {e}")
            print(traceback.format_exc())
            return False

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
        """执行汇总功能"""
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
                output_path = output_dir / f"现金流表_{timestamp}.xlsx"
            else:
                output_path = Path(output_path)
                output_dir = output_path.parent
        
            output_dir.mkdir(parents=True, exist_ok=True)
        
            template_path = self.get_template_path()
            if not template_path or not template_path.exists():
                print(f"❌ 模板文件不存在: {template_path}")
                return False
        
            if not output_path.exists():
                print(f"❌ 文件不存在: {output_path}")
                print("💡 请先运行'单文件生成'模式创建Sheet")
                return False
        
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
                        help='运行模式')
    parser.add_argument('--input', '-i', help='输入文件路径')
    parser.add_argument('--template', '-t', help='模板文件路径')
    parser.add_argument('--output', '-o', help='输出文件路径')
    parser.add_argument('--env', choices=['dev', 'test', 'prod'], default='dev')
    
    args = parser.parse_args()
    
    env_map = {'dev': Environment.DEVELOPMENT, 'test': Environment.TESTING, 'prod': Environment.PRODUCTION}
    env = env_map.get(args.env, Environment.DEVELOPMENT)
    
    generator = CashFlowReportGenerator(env)
    
    print("=" * 60)
    print("    现金流量报表生成器")
    print(f"    环境: {env.value}")
    print(f"    模式: {args.mode}")
    print("=" * 60)
    
    input_dir = generator.get_input_dir()
    if not input_dir.exists():
        input_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n📁 已创建 input 目录: {input_dir}")
        return 1
    
    if args.mode == 'summary':
        if args.input:
            input_files = [Path(args.input)]
        else:
            input_files = []
            for ext in generator.config.file.supported_extensions:
                input_files.extend(input_dir.glob(f"*{ext}"))
            input_files = [f for f in input_files if not f.name.startswith('~$')]
            input_files = sorted(input_files)
        
        if not input_files:
            print("❌ 没有找到Excel文件")
            return 1
        
        result = generator.run_summary(input_files, Path(args.output) if args.output else None)
        return 0 if result else 1
    
    if args.input:
        input_file = Path(args.input)
        if not input_file.exists():
            print(f"❌ 文件不存在: {input_file}")
            return 1
    else:
        input_files = []
        for ext in generator.config.file.supported_extensions:
            input_files.extend(input_dir.glob(f"*{ext}"))
        input_files = [f for f in input_files if not f.name.startswith('~$')]
        input_files = sorted(input_files)
        
        if not input_files:
            print("❌ 没有找到Excel文件")
            return 1
        
        input_file = input_files[0]
        print(f"\n📁 使用: {input_file.name}")
    
    if args.mode == 'template':
        generator.bank_name = input_file.stem
        generator.period_value = input_file.stem
        generator.sheet_name = input_file.stem
        generator.output_filename = f"{input_file.stem}.xlsx"
        result = generator.generate_template(input_file, generator.bank_name, generator.period_value, 
                                             generator.output_filename, generator.sheet_name)
        return 0 if result else 1
    
    if args.mode == 'fill':
        transactions = generator.load_transactions(input_file)
        if not generator.validate_transactions(transactions):
            return 1
        
        template_path = args.template or generator.template_path or str(generator.get_template_path())
        if not Path(template_path).exists():
            print(f"❌ 模板文件不存在: {template_path}")
            return 1
        
        result = generator.fill_data(template_path, transactions, input_file.stem)
        return 0 if result else 1
    
    if args.mode == 'report':
        transactions = generator.load_transactions(input_file)
        if not generator.validate_transactions(transactions):
            return 1
        
        result = generator.reporter.generate(generator.aggregator.aggregate(transactions), 
                                             args.output or str(generator.get_output_dir() / f"报表_{input_file.stem}.xlsx"))
        return 0 if result else 1
    
    # 完整流程
    generator.bank_name = input_file.stem
    generator.period_value = input_file.stem
    generator.sheet_name = input_file.stem
    generator.output_filename = f"{input_file.stem}.xlsx"
    success = generator.run_full_flow(input_file)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())