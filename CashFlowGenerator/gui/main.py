"""现金流量报表生成器 - 简洁版GUI"""

import sys
import yaml
import logging
import traceback
from pathlib import Path
from datetime import datetime
import re

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from CashFlowGenerator.config import Config, Environment

# ==================== 日志配置 ====================
LOG_FILE = PROJECT_ROOT / 'logs' / 'app.log'
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('CashFlowGenerator')


# ===== 硬编码白名单前缀 =====
ALLOW_PREFIXES = ["1122", "1123", "2202", "2203"]


class ConfigManager:
    """配置管理器 - 只负责读写 config.yaml"""
    
    def __init__(self):
        self.config_path = PROJECT_ROOT / 'config.yaml'
        self.config = {}
        self._load_config()
    
    def _load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"加载配置失败: {e}")
                self.config = {}
        return self.config
    
    def save_config(self, config):
        try:
            config['allow_prefixes'] = ALLOW_PREFIXES
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            self.config = config
            logger.info("配置已保存")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            raise


class WorkerThread(QThread):
    """后台工作线程 - 支持单文件生成和汇总模式"""
    progress_updated = pyqtSignal(int, str)
    log_updated = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    file_progress = pyqtSignal(int, int, str)
    
    def __init__(self, detail_paths, cashflow_file, mode="single"):
        super().__init__()
        self.detail_paths = detail_paths
        self.cashflow_file = cashflow_file
        self.mode = mode
        self._is_running = True
        self._start_time = None
    
    def stop(self):
        self._is_running = False
    
    def run(self):
        import time
        self._start_time = time.time()
        
        try:
            from main import CashFlowReportGenerator
            
            self.progress_updated.emit(5, "初始化...")
            self.log_updated.emit('▶ 开始运行')
            
            if self.mode == "summary":
                self.log_updated.emit(f'📊 汇总模式: 共 {len(self.detail_paths)} 个文件')
                self._run_summary()
            else:
                self.log_updated.emit(f'📁 单文件生成模式: 共 {len(self.detail_paths)} 个文件')
                self._run_single()
                
        except Exception as e:
            import traceback
            error_msg = str(e)
            error_detail = traceback.format_exc()
            self.log_updated.emit(f'❌ 错误: {error_msg}')
            self.log_updated.emit(f'📋 详细错误:\n{error_detail}')
            logger.error(f"生成失败: {error_msg}\n{error_detail}")
            self.finished.emit(False, error_msg)
    
    def _run_single(self):
        """单文件生成模式 - 每个文件生成一个Sheet"""
        import time
    
        from main import CashFlowReportGenerator
    
        config_obj = Config.get_instance(Environment.DEVELOPMENT)
        config_obj.reload_classification()
    
        classification = config_obj.data.classification
        expense_rules = classification.expense_rules
        allow_prefixes = getattr(classification, 'allow_prefixes', ALLOW_PREFIXES)
    
        self.log_updated.emit(f'📋 当前加载的支出规则: {len(expense_rules)} 条')
        for rule in expense_rules:
            keywords = []
            for cr in rule.contra_rules:
                keywords.extend(cr.keywords)
            if keywords:
                self.log_updated.emit(f'  - {rule.category}: {keywords}')
    
        self.log_updated.emit(f'✅ 白名单前缀（硬编码）: {allow_prefixes}')
        self.log_updated.emit(f'💡 所有收入统一归入"其他收入"')
    
        if self.cashflow_file:
            config_obj.file.output_dir = str(self.cashflow_file.parent)
    
        total_files = len(self.detail_paths)
        success_count = 0
        failed_files = []
    
        for idx, detail_path in enumerate(self.detail_paths, 1):
            if not self._is_running:
                self.finished.emit(False, "已停止")
                return
        
            detail_name = detail_path.stem
            self.file_progress.emit(idx, total_files, detail_name)
            self.log_updated.emit('')
            self.log_updated.emit('=' * 50)
            self.log_updated.emit(f'📄 处理 [{idx}/{total_files}]: {detail_path.name}')
            self.log_updated.emit('=' * 50)
        
            progress_base = 5 + int((idx - 1) / total_files * 85)
            self.progress_updated.emit(progress_base, f"处理中: {detail_name}")
        
            try:
                generator = CashFlowReportGenerator(Environment.DEVELOPMENT)
            
                generator.bank_name = detail_name
                generator.period_value = detail_name
                generator.sheet_name = detail_name
                generator.output_filename = f"{detail_name}.xlsx"
            
                generator.set_output_path(self.cashflow_file)
            
                self.log_updated.emit(f'📄 Sheet名称: {detail_name}')
            
                transactions = generator.load_transactions(detail_path)
                self.log_updated.emit(f'📊 加载 {len(transactions)} 笔交易')
            
                if not self._is_running:
                    self.finished.emit(False, "已停止")
                    return
            
                if len(transactions) == 0:
                    self.log_updated.emit(f'⚠️ 没有找到交易数据，将创建空Sheet')
            
                generator.transactions = transactions
            
                success = generator.run_full_flow(detail_path)
            
                if success:
                    success_count += 1
                    self.log_updated.emit(f'✅ {detail_name} 处理完成')
                else:
                    self.log_updated.emit(f'❌ {detail_name} 处理失败')
                    failed_files.append((detail_path.name, "生成失败"))
            
            except Exception as e:
                self.log_updated.emit(f'❌ 处理失败: {str(e)}')
                failed_files.append((detail_path.name, str(e)))
    
        elapsed = time.time() - self._start_time
        self.progress_updated.emit(100, "完成!")
    
        self.log_updated.emit('')
        self.log_updated.emit('=' * 50)
        self.log_updated.emit('📊 批量处理完成')
        self.log_updated.emit(f'  成功: {success_count}/{total_files}')
        if failed_files:
            self.log_updated.emit(f'  失败: {len(failed_files)} 个')
            for name, err in failed_files:
                self.log_updated.emit(f'    - {name}: {err}')
        self.log_updated.emit(f'⏱️ 总耗时: {elapsed:.1f} 秒')
        self.log_updated.emit('=' * 50)
    
        self.finished.emit(True, f"成功 {success_count}/{total_files} 个文件") 
    
    def _run_summary(self):
        """汇总模式 - 所有文件汇总到汇总表"""
        import time
        
        from main import CashFlowReportGenerator
        
        config_obj = Config.get_instance(Environment.DEVELOPMENT)
        config_obj.reload_classification()
        
        generator = CashFlowReportGenerator(Environment.DEVELOPMENT)
        generator.set_output_path(self.cashflow_file)
        
        self.log_updated.emit(f'📄 输出文件: {self.cashflow_file}')
        self.log_updated.emit(f'📁 共 {len(self.detail_paths)} 个明细账文件')
        
        for idx, path in enumerate(self.detail_paths, 1):
            self.log_updated.emit(f'  [{idx}] {path.name}')
        
        self.progress_updated.emit(30, "执行汇总...")
        
        success = generator.run_summary(self.detail_paths, self.cashflow_file)
        
        if success:
            elapsed = time.time() - self._start_time
            self.progress_updated.emit(100, "完成!")
            self.log_updated.emit(f'✅ 汇总完成: {self.cashflow_file}')
            self.log_updated.emit(f'⏱️ 总耗时: {elapsed:.1f} 秒')
            self.finished.emit(True, str(self.cashflow_file))
        else:
            self.finished.emit(False, "汇总失败")
    
    


class MainWindow(QMainWindow):
    """主窗口 - 简洁版"""
    
    BTN_WIDTH = 100
    BTN_HEIGHT = 32
    BTN_RADIUS = 6
    BTN_FONT_SIZE = 13
    
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings('Weiyu', 'CashFlowGenerator')
        
        self.config_obj = Config.get_instance(Environment.DEVELOPMENT)
        self.config_obj.reload_classification()
        self.config_obj.data.classification.allow_prefixes = ALLOW_PREFIXES
        
        self.config_manager = ConfigManager()
        
        # 两个Tab的独立Worker
        self.single_worker = None
        self.summary_worker = None
        
        self.recent_files = self.settings.value('recent_files', []) or []
        
        # 两个Tab独立文件列表
        self.single_files = []
        self.summary_files = []
        
        self.ui_config = self.config_obj.ui
        
        # 先初始化控件
        self._init_controls()
        # 再初始化UI
        self.init_ui()
        self.load_config()
        self.restore_window()
        self.update_recent_menu()
    
    def _init_controls(self):
        """初始化所有控件"""
        # 单文件生成Tab控件
        self.single_detail_path = QLineEdit()
        self.single_cashflow_path = QLineEdit()
        self.single_file_list = QListWidget()
        self.single_file_count_label = QLabel('共 0 个文件')
    
        # 汇总模式Tab控件
        self.summary_detail_path = QLineEdit()
        self.summary_cashflow_path = QLineEdit()
        self.summary_file_list = QListWidget()
        self.summary_file_count_label = QLabel('共 0 个文件')
    
        # ===== 添加 mode_hint =====
        self.mode_hint = QLabel('💡 选择目录 → 每次创建新文件（含时间戳） | 选择已有文件 → 追加Sheet')
        self.mode_hint.setStyleSheet('color: #94a3b8; font-size: 13px; padding: 4px 0 0 0;')
    
        # 公共控件
        self.expense_rules = QTextEdit()
        self.log_text = QTextEdit()
        self.progress_bar = QProgressBar()
        self.progress_label = QLabel('就绪')
        self.run_btn = None
        self.stop_btn = None
        self.tabs = QTabWidget() 
    
    # ==================== 窗口管理 ====================
    def restore_window(self):
        geo = self.settings.value('window_geometry')
        if geo:
            self.restoreGeometry(geo)
    
    def save_window(self):
        self.settings.setValue('window_geometry', self.saveGeometry())
    
    def closeEvent(self, event):
        self.save_window()
        if self.single_worker and self.single_worker.isRunning():
            self.single_worker.stop()
            self.single_worker.wait()
        if self.summary_worker and self.summary_worker.isRunning():
            self.summary_worker.stop()
            self.summary_worker.wait()
        super().closeEvent(event)
    
    # ==================== 菜单栏 ====================
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu('文件(&F)')
        self.recent_menu = QMenu('最近文件(&R)', self)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        save_action = QAction('保存配置(&S)', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.save_config)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        exit_action = QAction('退出(&X)', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        tools_menu = menubar.addMenu('工具(&T)')
        preview_action = QAction('数据预览(&P)', self)
        preview_action.setShortcut('Ctrl+P')
        preview_action.triggered.connect(self.preview_data)
        tools_menu.addAction(preview_action)
        validate_action = QAction('验证规则(&V)', self)
        validate_action.triggered.connect(self.validate_rules)
        tools_menu.addAction(validate_action)
        
        help_menu = menubar.addMenu('帮助(&H)')
        about_action = QAction('关于(&A)', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def update_recent_menu(self):
        self.recent_menu.clear()
        if not self.recent_files:
            no_action = QAction('(无最近文件)', self)
            no_action.setEnabled(False)
            self.recent_menu.addAction(no_action)
            return
        
        for path in self.recent_files[:10]:
            action = QAction(Path(path).name, self)
            action.setToolTip(path)
            action.triggered.connect(lambda checked, p=path: self.open_recent(p))
            self.recent_menu.addAction(action)
        
        self.recent_menu.addSeparator()
        clear_action = QAction('清空列表', self)
        clear_action.triggered.connect(self.clear_recent)
        self.recent_menu.addAction(clear_action)
    
    def open_recent(self, path):
        if Path(path).exists():
            current_tab = self.tabs.currentIndex()
            if current_tab == 0:
                self.single_files = [Path(path)]
                self.update_file_list(self.single_file_list, self.single_files, self.single_file_count_label)
            else:
                self.summary_files = [Path(path)]
                self.update_file_list(self.summary_file_list, self.summary_files, self.summary_file_count_label)
            self.append_log(f'📁 打开: {Path(path).name}')
            self.auto_save()
        else:
            self.recent_files.remove(path)
            self.update_recent_menu()
    
    def clear_recent(self):
        self.recent_files = []
        self.settings.setValue('recent_files', self.recent_files)
        self.update_recent_menu()
    
    def add_recent(self, paths):
        for path in paths:
            if path in self.recent_files:
                self.recent_files.remove(path)
            self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:10]
        self.settings.setValue('recent_files', self.recent_files)
        self.update_recent_menu()
    
    def validate_rules(self):
        is_valid, errors = self._check_rules()
        if is_valid:
            QMessageBox.information(self, '验证通过', '✅ 规则格式正确')
            return True
        else:
            error_msg = "支出规则存在语法错误，请修正后重试：\n\n"
            for err in errors:
                error_msg += f"  • {err}\n"
            error_msg += "\n💡 请根据提示修正后重新验证"
            QMessageBox.warning(self, '规则错误', error_msg)
            return False
    
    def preview_data(self):
        """预览当前Tab选中的第一个文件"""
        current_tab = self.tabs.currentIndex()
        if current_tab == 0:
            files = self.single_files
        else:
            files = self.summary_files
        
        if not files:
            QMessageBox.warning(self, '提示', '请先选择明细账文件')
            return
        
        path = str(files[0])
        if not Path(path).exists():
            QMessageBox.warning(self, '提示', '文件不存在')
            return
        
        try:
            from services.data_loader import DataLoader
            loader = DataLoader(Config.get_instance())
            transactions = loader.load_from_files([path])
            
            if not transactions:
                QMessageBox.warning(self, '提示', '没有交易数据')
                return
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f'数据预览 ({Path(path).name}) - {len(transactions)}笔')
            dialog.resize(850, 500)
            
            layout = QVBoxLayout(dialog)
            
            info = QLabel(f'文件: {Path(path).name} | 总计 {len(transactions)} 笔 | 收入 {len([t for t in transactions if t.is_income])} 笔 | 支出 {len([t for t in transactions if not t.is_income])} 笔')
            layout.addWidget(info)
            
            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(['日期', '摘要', '对方科目', '金额', '类型'])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            table.setAlternatingRowColors(True)
            
            show = min(len(transactions), 200)
            table.setRowCount(show)
            for i, t in enumerate(transactions[:show]):
                table.setItem(i, 0, QTableWidgetItem(t.date.strftime('%Y-%m-%d') if t.date else ''))
                table.setItem(i, 1, QTableWidgetItem(t.description[:25] if hasattr(t, 'description') else ''))
                table.setItem(i, 2, QTableWidgetItem(t.contra_subject[:20] if hasattr(t, 'contra_subject') else ''))
                table.setItem(i, 3, QTableWidgetItem(f"{float(t.amount):,.2f}"))
                table.setItem(i, 4, QTableWidgetItem('收入' if t.is_income else '支出'))
            
            layout.addWidget(table)
            
            if len(transactions) > 200:
                layout.addWidget(QLabel(f'⚠️ 仅显示前200笔'))
            
            btn = QPushButton('关闭')
            btn.clicked.connect(dialog.accept)
            layout.addWidget(btn, alignment=Qt.AlignRight)
            
            dialog.exec_()
            
        except Exception as e:
            QMessageBox.critical(self, '错误', f'预览失败: {e}')
    
    def _log_rules(self):
        """在日志中展示当前规则"""
        classification = self.config_obj.data.classification
        expense_rules = classification.expense_rules
        allow_prefixes = getattr(classification, 'allow_prefixes', ALLOW_PREFIXES)

        self.append_log('')
        self.append_log('=' * 60)
        
        # ===== 收入规则 - 固定显示"其他收入" =====
        self.append_log('📋 当前收入规则（固定）:')
        self.append_log('  其他收入: 所有收入统一归入此分类')
        
        self.append_log('')
        self.append_log('📋 当前加载的支出规则:')
        if expense_rules:
            for rule in expense_rules:
                keywords = []
                for cr in rule.contra_rules:
                    keywords.extend(cr.keywords)
                keywords.extend(rule.summary_keywords)
                if keywords:
                    self.append_log(f'  {rule.category}: {keywords}')
        else:
            self.append_log('  (无支出规则)')

        self.append_log('')
        self.append_log('✅ 白名单前缀（硬编码）:')
        self.append_log(f'  {allow_prefixes}')
        self.append_log('💡 只有对方科目以这些前缀开头的交易才会填充客户/供应商列')
        self.append_log('=' * 60)
        self.append_log('')
    
    def save_config(self):
        try:
            config = self.build_config()
            config['allow_prefixes'] = ALLOW_PREFIXES
            self.config_manager.save_config(config)
            self.config_obj.reload_classification()
            self.config_obj.data.classification.allow_prefixes = ALLOW_PREFIXES
            self._log_rules()
            self.append_log('💾 配置已保存并重新加载')
            QMessageBox.information(self, '完成', '配置已保存并生效')
        except Exception as e:
            QMessageBox.critical(self, '错误', f'保存失败: {e}')
    
    def show_about(self):
        QMessageBox.about(self, '关于', 
            '📊 现金流量报表生成器\n\n'
            '版本 1.0\n\n'
            '支持两种模式:\n'
            '  📄 单文件生成 - 每个文件生成独立Sheet\n'
            '  📊 汇总模式 - 所有文件汇总到汇总表\n\n'
            '快捷键:\n'
            '  Ctrl+P  数据预览\n'
            '  Ctrl+R  运行\n'
            '  Ctrl+S  保存配置'
        )
    
    # ==================== UI ====================
    def init_ui(self):
        self.setWindowTitle('现金流量报表生成器')
        self.setMinimumSize(1100, 680)
        self.resize(1100, 680)
        
        font = QFont("Microsoft YaHei", 10)
        QApplication.setFont(font)
        
        self.setStyleSheet(self._get_style())
        self.create_menu_bar()
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(14)
        layout.setContentsMargins(30, 14, 30, 20)
        
        # 标题
        title = QLabel('📊 现金流量报表生成器')
        title.setStyleSheet('font-size: 24px; font-weight: bold; color: #0f172a; padding: 6px 0 12px 0;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Tab
        self.tabs.addTab(self.create_single_tab(), '📄 单文件生成')
        self.tabs.addTab(self.create_summary_tab(), '📊 汇总模式')
        self.tabs.addTab(self.create_rules_tab(), '📌 支出规则')
        self.tabs.addTab(self.create_whitelist_tab(), '✅ 白名单')
        self.tabs.addTab(self.create_log_tab(), '📝 日志')
        layout.addWidget(self.tabs)
        
        # ===== 底部区域 =====
        bottom_widget = QWidget()
        bottom_widget.setStyleSheet("""
            QWidget {
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(16, 8, 16, 8)
        bottom_layout.setSpacing(16)
        
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat('%p%')
        self.progress_bar.setFixedHeight(32)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 6px;
                background: #f1f5f9;
                text-align: center;
                font-weight: 600;
                font-size: 13px;
                color: #1e293b;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4f46e5, stop:1 #059669);
                border-radius: 6px;
            }
        """)
        bottom_layout.addWidget(self.progress_bar, 1)
        
        self.progress_label.setFixedWidth(80)
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("""
            QLabel {
                color: #64748b;
                font-size: 13px;
                font-weight: 500;
                background: transparent;
                border: none;
            }
        """)
        bottom_layout.addWidget(self.progress_label)
        
        self.run_btn = self._create_button('▶ 运行', '#059669', '#047857', '#94a3b8')
        self.run_btn.clicked.connect(self.run_generator)
        bottom_layout.addWidget(self.run_btn)

        self.stop_btn = self._create_button('⏹ 停止', '#dc2626', '#b91c1c', '#cbd5e1')
        self.stop_btn.clicked.connect(self.stop_generator)
        self.stop_btn.setEnabled(False)
        bottom_layout.addWidget(self.stop_btn)
        
        layout.addWidget(bottom_widget)
        
        # 快捷键
        QShortcut(QKeySequence('Ctrl+P'), self, self.preview_data)
        QShortcut(QKeySequence('Ctrl+R'), self, self.run_generator)
        QShortcut(QKeySequence('Ctrl+S'), self, self.save_config)
    
    def _create_button(self, text, bg_color, hover_color, disabled_color):
        btn = QPushButton(text)
        btn.setFixedSize(self.BTN_WIDTH, self.BTN_HEIGHT)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                color: white;
                border: none;
                border-radius: {self.BTN_RADIUS}px;
                font-weight: 600;
                font-size: {self.BTN_FONT_SIZE}px;
            }}
            QPushButton:hover {{ background: {hover_color}; }}
            QPushButton:disabled {{ 
                background: {bg_color};
                opacity: 0.6;
            }}
        """)
        return btn
    
    def _get_style(self):
        return """
            QMainWindow { background: #f1f5f9; }
            
            QTabWidget::pane {
                border: 0px solid #e2e8f0;
                background: white;
                border-radius: 0 12px 12px 12px;
                padding: 6px;
                margin-top: -1px;
            }
            QTabBar::tab {
                background: #f1f5f9;
                padding: 10px 24px;
                margin-right: 2px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-size: 14px;
                color: #64748b;
            }
            QTabBar::tab:selected {
                background: white;
                color: #4f46e5;
                border: none;
            }
            
            QGroupBox {
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 16px;
                background: white;
            }
            QGroupBox::title {
                left: 16px;
                padding: 0 12px;
                color: #0f172a;
                font-size: 15px;
                font-weight: 600;
            }
            
            QLabel {
                color: #1e293b;
                font-size: 14px;
                min-height: 30px;
            }
            
            QLineEdit {
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 14px;
                background: white;
                min-height: 20px;
                color: #1e293b;
            }
            QLineEdit:focus { border-color: #4f46e5; }
            QLineEdit:hover { border-color: #94a3b8; }
            QLineEdit:disabled { background: #f1f5f9; color: #94a3b8; }
            QLineEdit#placeholder {
                background: #f8fafc;
                color: #94a3b8;
            }
            QLineEdit#placeholder:focus { border-color: #e2e8f0; }
            
            QTextEdit {
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 15px;
                padding: 12px;
                background: white;
                font-family: 'Consolas', monospace;
                line-height: 1.6;
                color: #1e293b;
            }
            QTextEdit:focus { border-color: #4f46e5; }
            
            QPushButton#toolBtn {
                background: #f1f5f9;
                color: #1e293b;
                border: 1px solid #e2e8f0;
                padding: 6px 16px;
                font-size: 13px;
                border-radius: 6px;
                min-height: 30px;
            }
            QPushButton#toolBtn:hover { background: #e5e7eb; }
            
            QProgressBar {
                border: none;
                border-radius: 6px;
                background: #f1f5f9;
                text-align: center;
                font-weight: 600;
                font-size: 13px;
                color: #1e293b;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4f46e5, stop:1 #059669);
                border-radius: 6px;
            }
            
            QScrollBar:vertical {
                border: none;
                background: #f1f5f9;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #94a3b8; }
            
            QMenuBar {
                background: #f8fafc;
                border-bottom: 1px solid #e2e8f0;
            }
            QMenuBar::item {
                padding: 6px 12px;
                font-size: 14px;
            }
            QMenuBar::item:selected {
                background: #4f46e5;
                color: white;
            }
            QMenu {
                background: white;
                border: 1px solid #e2e8f0;
                padding: 6px;
            }
            QMenu::item {
                padding: 6px 30px;
                font-size: 14px;
            }
            QMenu::item:selected {
                background: #4f46e5;
                color: white;
            }
            
            QListWidget {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 4px;
                font-size: 13px;
                background: #f8fafc;
            }
            QListWidget::item {
                padding: 4px 8px;
            }
        """
    
    def _create_file_selector(self, line_edit, placeholder_text):
        """创建文件选择器组件"""
        container = QHBoxLayout()
        container.setSpacing(10)
        
        line_edit.setObjectName('placeholder')
        line_edit.setPlaceholderText(placeholder_text)
        line_edit.setReadOnly(True)
        line_edit.setFixedHeight(self.BTN_HEIGHT)
        line_edit.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 2px 14px;
                font-size: 14px;
                background: #f8fafc;
                color: #94a3b8;
                height: {self.BTN_HEIGHT}px;
            }}
            QLineEdit:focus {{ border-color: #4f46e5; }}
        """)
        container.addWidget(line_edit, 1)
        
        btn = self._create_tool_button('📂 选择')
        container.addWidget(btn, 0, Qt.AlignVCenter)
        
        return container, btn
    
    def _create_tool_button(self, text):
        btn = QPushButton(text)
        btn.setObjectName('toolBtn')
        btn.setFixedSize(self.BTN_WIDTH, self.BTN_HEIGHT)
        btn.setStyleSheet(f"""
            QPushButton#toolBtn {{
                background: #f1f5f9;
                color: #1e293b;
                border: 2px solid #e2e8f0;
                border-radius: {self.BTN_RADIUS}px;
                font-size: {self.BTN_FONT_SIZE}px;
                font-weight: 500;
                padding: 3px 8px;
                margin-top: 8px;
            }}
            QPushButton#toolBtn:hover {{ background: #e5e7eb; }}
        """)
        return btn
    
    def select_files(self, file_list, line_edit, list_widget, count_label):
        """选择多个文件"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, 
            '选择明细账文件（按住Ctrl多选）', 
            '',
            'Excel文件 (*.xlsx *.xls)'
        )
        if paths:
            paths = sorted(paths)
            existing_paths = {str(p) for p in file_list}
            for path in paths:
                if path not in existing_paths:
                    file_list.append(Path(path))
                    existing_paths.add(path)
            
            self.update_file_list(list_widget, file_list, count_label)
            self.add_recent(paths)
            self.append_log(f'📁 添加了 {len(paths)} 个明细账文件')
            self.auto_save()
    
    def update_file_list(self, list_widget, file_list, count_label):
        """更新文件列表显示"""
        list_widget.clear()
        for path in file_list:
            list_widget.addItem(path.name)
        
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item:
                item.setToolTip(str(file_list[i]))
        
        if file_list:
            count_label.setText(f'共 {len(file_list)} 个文件')
        else:
            count_label.setText('共 0 个文件')
    
    def clear_file_list(self, file_list, list_widget, count_label, log_msg):
        """清空文件列表"""
        file_list.clear()
        self.update_file_list(list_widget, file_list, count_label)
        self.append_log(log_msg)
    
    def select_cashflow_target(self, line_edit):
        """选择输出位置"""
        msg = QMessageBox(self)
        msg.setWindowTitle('选择输出位置')
        msg.setText('请选择操作模式：')
        dir_btn = msg.addButton('📂 选择输出目录（创建新文件）', QMessageBox.ActionRole)
        file_btn = msg.addButton('📄 选择已有文件（追加Sheet）', QMessageBox.ActionRole)
        cancel_btn = msg.addButton('取消', QMessageBox.RejectRole)
        msg.exec_()
        
        clicked = msg.clickedButton()
        
        if clicked == cancel_btn:
            return
        
        elif clicked == dir_btn:
            current = line_edit.text().strip()
            if current and Path(current).suffix in ['.xlsx', '.xls']:
                current = str(Path(current).parent)
            elif not current:
                current = str(Path.home() / 'Desktop')
            
            path = QFileDialog.getExistingDirectory(
                self, 
                '选择输出目录（将创建新文件）', 
                current
            )
            if path:
                line_edit.setText(path)
                line_edit.setStyleSheet('background: white; color: #1e293b;')
                self.mode_hint.setText('💡 目录模式 → 每次运行创建新文件（含时间戳）')
                self.append_log(f'📂 输出目录: {path}')
                self.auto_save()
        
        elif clicked == file_btn:
            current = line_edit.text().strip()
            current_dir = ''
            if current:
                p = Path(current)
                if p.suffix in ['.xlsx', '.xls']:
                    current_dir = str(p.parent)
                elif p.is_dir():
                    current_dir = str(p)
            
            path, _ = QFileDialog.getOpenFileName(
                self, 
                '选择已有文件（追加Sheet）', 
                current_dir,
                'Excel文件 (*.xlsx *.xls)'
            )
            if path:
                line_edit.setText(path)
                line_edit.setStyleSheet('background: white; color: #1e293b;')
                self.mode_hint.setText('💡 文件模式 → 在已有文件中追加Sheet')
                self.append_log(f'📄 选择文件: {Path(path).name}')
                self.auto_save()
    
    # ==================== 单文件生成Tab ====================
    def create_single_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        layout.setContentsMargins(40, 22, 40, 22)
        
        g2 = QGroupBox('文件路径')
        g2.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 16px;
                background: white;
            }
            QGroupBox::title {
                left: 16px;
                padding: 0 12px;
                color: #0f172a;
                font-size: 15px;
                font-weight: 600;
            }
        """)
        
        f2 = QFormLayout()
        f2.setVerticalSpacing(16)
        f2.setHorizontalSpacing(20)
        f2.setContentsMargins(28, 20, 28, 18)
        
        # 明细账
        detail_container, detail_btn = self._create_file_selector(
            self.single_detail_path,
            '点击右侧按钮选择明细账文件（支持Ctrl多选）'
        )
        detail_btn.clicked.connect(lambda: self.select_files(
            self.single_files, self.single_detail_path, 
            self.single_file_list, self.single_file_count_label
        ))
        f2.addRow('明细账：', detail_container)
        
        # 现金流表
        cashflow_container = QHBoxLayout()
        cashflow_container.setSpacing(10)
        
        self.single_cashflow_path.setObjectName('placeholder')
        self.single_cashflow_path.setPlaceholderText('选择输出目录 或 已有现金流表文件')
        self.single_cashflow_path.setReadOnly(True)
        self.single_cashflow_path.setFixedHeight(self.BTN_HEIGHT)
        self.single_cashflow_path.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 2px 14px;
                font-size: 14px;
                background: #f8fafc;
                color: #94a3b8;
                height: {self.BTN_HEIGHT}px;
            }}
            QLineEdit:focus {{ border-color: #4f46e5; }}
        """)
        cashflow_container.addWidget(self.single_cashflow_path, 1)
        
        cashflow_btn = self._create_tool_button('📂 选择')
        cashflow_btn.clicked.connect(lambda: self.select_cashflow_target(self.single_cashflow_path))
        cashflow_container.addWidget(cashflow_btn, 0, Qt.AlignVCenter)
        
        f2.addRow('现金流表：', cashflow_container)
        
        mode_hint = QLabel('💡 选择目录 → 每次创建新文件（含时间戳） | 选择已有文件 → 追加Sheet')
        mode_hint.setStyleSheet('color: #94a3b8; font-size: 13px; padding: 4px 0 0 0;')
        f2.addRow('', mode_hint)
        
        # 文件列表
        file_list_label = QLabel('📋 已选择的明细账文件：')
        file_list_label.setStyleSheet('font-weight: 600; color: #0f172a; font-size: 14px; padding-top: 8px;')
        f2.addRow('', file_list_label)
        
        self.single_file_list.setFixedHeight(80)
        f2.addRow('', self.single_file_list)
        
        file_btn_layout = QHBoxLayout()
        file_btn_layout.setSpacing(10)
        
        clear_btn = self._create_tool_button('🗑 清空列表')
        clear_btn.clicked.connect(lambda: self.clear_file_list(
            self.single_files, self.single_file_list, 
            self.single_file_count_label, '🗑 已清空文件列表'
        ))
        file_btn_layout.addWidget(clear_btn)
        
        file_btn_layout.addStretch()
        
        self.single_file_count_label.setStyleSheet('color: #64748b; font-size: 13px;')
        file_btn_layout.addWidget(self.single_file_count_label)
        
        f2.addRow('', file_btn_layout)
        
        g2.setLayout(f2)
        layout.addWidget(g2)
        
        layout.addStretch()
        return widget
    
    # ==================== 汇总模式Tab ====================
    def create_summary_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        layout.setContentsMargins(40, 22, 40, 22)
        
        g2 = QGroupBox('文件路径')
        g2.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 16px;
                background: white;
            }
            QGroupBox::title {
                left: 16px;
                padding: 0 12px;
                color: #0f172a;
                font-size: 15px;
                font-weight: 600;
            }
        """)
        
        f2 = QFormLayout()
        f2.setVerticalSpacing(16)
        f2.setHorizontalSpacing(20)
        f2.setContentsMargins(28, 20, 28, 18)
        
        # 明细账
        detail_container, detail_btn = self._create_file_selector(
            self.summary_detail_path,
            '点击右侧按钮选择明细账文件（支持Ctrl多选）'
        )
        detail_btn.clicked.connect(lambda: self.select_files(
            self.summary_files, self.summary_detail_path, 
            self.summary_file_list, self.summary_file_count_label
        ))
        f2.addRow('明细账：', detail_container)
        
        # 汇总表
        cashflow_container = QHBoxLayout()
        cashflow_container.setSpacing(10)
        
        self.summary_cashflow_path.setObjectName('placeholder')
        self.summary_cashflow_path.setPlaceholderText('选择输出目录 或 已有汇总表文件')
        self.summary_cashflow_path.setReadOnly(True)
        self.summary_cashflow_path.setFixedHeight(self.BTN_HEIGHT)
        self.summary_cashflow_path.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 2px 14px;
                font-size: 14px;
                background: #f8fafc;
                color: #94a3b8;
                height: {self.BTN_HEIGHT}px;
            }}
            QLineEdit:focus {{ border-color: #4f46e5; }}
        """)
        cashflow_container.addWidget(self.summary_cashflow_path, 1)
        
        cashflow_btn = self._create_tool_button('📂 选择')
        cashflow_btn.clicked.connect(lambda: self.select_cashflow_target(self.summary_cashflow_path))
        cashflow_container.addWidget(cashflow_btn, 0, Qt.AlignVCenter)
        
        f2.addRow('汇总表：', cashflow_container)
        
        mode_hint = QLabel('💡 选择目录 → 每次创建新文件（含时间戳） | 选择已有文件 → 追加Sheet')
        mode_hint.setStyleSheet('color: #4f46e5; font-size: 13px; padding: 4px 0 0 0;')
        f2.addRow('', mode_hint)
        
        # 文件列表
        file_list_label = QLabel('📋 已选择的明细账文件：')
        file_list_label.setStyleSheet('font-weight: 600; color: #0f172a; font-size: 14px; padding-top: 8px;')
        f2.addRow('', file_list_label)
        
        self.summary_file_list.setFixedHeight(80)
        f2.addRow('', self.summary_file_list)
        
        file_btn_layout = QHBoxLayout()
        file_btn_layout.setSpacing(10)
        
        clear_btn = self._create_tool_button('🗑 清空列表')
        clear_btn.clicked.connect(lambda: self.clear_file_list(
            self.summary_files, self.summary_file_list, 
            self.summary_file_count_label, '🗑 已清空汇总模式文件列表'
        ))
        file_btn_layout.addWidget(clear_btn)
        
        file_btn_layout.addStretch()
        
        self.summary_file_count_label.setStyleSheet('color: #64748b; font-size: 13px;')
        file_btn_layout.addWidget(self.summary_file_count_label)
        
        f2.addRow('', file_btn_layout)
        
        g2.setLayout(f2)
        layout.addWidget(g2)
        
        layout.addStretch()
        return widget
    
    # ==================== 支出规则Tab ====================
    def create_rules_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(40, 18, 40, 18)
        
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        
        validate_btn = self._create_tool_button('校验')
        validate_btn.clicked.connect(self.validate_rules)
        toolbar.addWidget(validate_btn)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        hint = QLabel('格式: 分类名称:关键词1,关键词2,关键词3  (每行一条)')
        hint.setStyleSheet('color: #94a3b8; font-size: 13px;')
        layout.addWidget(hint)
        
        self.expense_rules.setPlaceholderText(
            '示例:\n'
            '主营业务支出_商品采购:付供应商款,采购款,货款\n'
            '主营业务支出_运费:运费,快递,物流,顺丰\n'
            '财务费用_手续费:银行手续费,手续费'
        )
        self.expense_rules.setMinimumHeight(360)
        layout.addWidget(self.expense_rules)
        
        return widget
    
    # ==================== 白名单Tab ====================
    def create_whitelist_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(40, 18, 40, 18)
        
        info_box = QGroupBox('📋 白名单规则（硬编码，不可编辑）')
        info_box.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 16px;
                background: #f8fafc;
            }
            QGroupBox::title {
                left: 16px;
                padding: 0 12px;
                color: #0f172a;
                font-size: 15px;
                font-weight: 600;
            }
        """)
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(28, 20, 28, 18)
        info_layout.setSpacing(12)
        
        desc = QLabel(
            '只有对方科目以以下前缀开头的交易，才会填充到「客户/供应商」列：'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet('color: #1e293b; font-size: 14px;')
        info_layout.addWidget(desc)
        
        prefixes_widget = QWidget()
        prefixes_layout = QHBoxLayout(prefixes_widget)
        prefixes_layout.setSpacing(16)
        prefixes_layout.setContentsMargins(0, 8, 0, 8)
        
        prefix_info = [
            ("1122", "应收账款"),
            ("1123", "预付账款"),
            ("2202", "应付账款"),
            ("2203", "预收账款"),
        ]
        
        for code, name in prefix_info:
            label = QLabel(f'<b>{code}</b>  →  {name}')
            label.setStyleSheet("""
                QLabel {
                    background: white;
                    border: 2px solid #4f46e5;
                    border-radius: 8px;
                    padding: 10px 16px;
                    font-size: 14px;
                    color: #0f172a;
                    min-width: 120px;
                }
            """)
            label.setAlignment(Qt.AlignCenter)
            prefixes_layout.addWidget(label)
        
        prefixes_layout.addStretch()
        info_layout.addWidget(prefixes_widget)
        
        tip = QLabel(
            '💡 示例：对方科目为 "112201_应收账款_某某公司"  →  会填充客户/供应商列\n'
            '   对方科目为 "管理费用"  →  不会填充客户/供应商列'
        )
        tip.setWordWrap(True)
        tip.setStyleSheet('color: #64748b; font-size: 13px; background: white; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px;')
        info_layout.addWidget(tip)
        
        layout.addWidget(info_box)
        layout.addStretch()
        
        return widget
    
    # ==================== 日志Tab ====================
    def create_log_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(30, 16, 30, 16)
        
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', monospace;
                font-size: 14px;
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 18px;
                min-height: 370px;
            }
        """)
        layout.addWidget(self.log_text)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        clear_btn = self._create_tool_button('清空日志')
        clear_btn.clicked.connect(lambda: self.log_text.clear())
        btn_layout.addWidget(clear_btn)
        layout.addLayout(btn_layout)
        
        return widget
    
    # ==================== 配置 ====================
    def load_config(self):
        classification = self.config_obj.data.classification
        yaml_config = self.config_manager.config
    
        classification.allow_prefixes = ALLOW_PREFIXES
    
        file_cfg = yaml_config.get('file', {})
        
        # 加载单文件生成模式
        single_files = file_cfg.get('single_files', [])
        if single_files:
            self.single_files = [Path(p) for p in single_files if Path(p).exists()]
            self.update_file_list(self.single_file_list, self.single_files, self.single_file_count_label)
        
        # 加载汇总模式
        summary_files = file_cfg.get('summary_files', [])
        if summary_files:
            self.summary_files = [Path(p) for p in summary_files if Path(p).exists()]
            self.update_file_list(self.summary_file_list, self.summary_files, self.summary_file_count_label)
        
        # 加载单文件生成现金流路径
        single_cashflow = file_cfg.get('single_cashflow_file', '')
        if single_cashflow:
            self.single_cashflow_path.setText(single_cashflow)
            self.single_cashflow_path.setStyleSheet('background: white; color: #1e293b;')
        
        # 加载汇总模式现金流路径
        summary_cashflow = file_cfg.get('summary_cashflow_file', '')
        if summary_cashflow:
            self.summary_cashflow_path.setText(summary_cashflow)
            self.summary_cashflow_path.setStyleSheet('background: white; color: #1e293b;')
    
        # 加载支出规则
        expense_rules = classification.expense_rules
        if expense_rules:
            lines = []
            for rule in expense_rules:
                keywords = []
                for cr in rule.contra_rules:
                    keywords.extend(cr.keywords)
                keywords.extend(rule.summary_keywords)
                if keywords:
                    lines.append(f"{rule.category}:{','.join(keywords)}")
            self.expense_rules.setText('\n'.join(lines))
        else:
            self.expense_rules.setText('')
    
        self.append_log('📂 配置加载完成')
        self._log_rules()
    
    def build_config(self):
        rules = []
        for line in self.expense_rules.toPlainText().split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
            parts = line.split(':', 1)
            category = parts[0].strip()
            keywords = [k.strip() for k in parts[1].split(',') if k.strip()]
            if category and keywords:
                rules.append({
                    'category': category,
                    'contra_keywords': keywords,
                    'summary_keywords': [],
                    'enabled': True
                })
        
        return {
            'app': {
                'period_value': '',
                'decimal_places': 2,
                'validation_threshold': 0.01
            },
            'company': {'banks': []},
            'file': {
                'single_files': [str(p) for p in self.single_files],
                'summary_files': [str(p) for p in self.summary_files],
                'single_cashflow_file': self.single_cashflow_path.text().strip(),
                'summary_cashflow_file': self.summary_cashflow_path.text().strip()
            },
            'income_rules': self.config_manager.config.get('income_rules', []),
            'expense_rules': rules,
            'allow_prefixes': ALLOW_PREFIXES,
            'column_mapping': {
                '产品收入': 15,
                '服务收入': 16,
                '其他收入': 17,
                '主营业务支出_商品采购': 22,
                '主营业务支出_运费': 23,
                '主营业务支出_服务费': 24,
                '主营业务支出_返点佣金': 25,
                '研发费用_人工成本': 26,
                '研发费用_材料设备': 27,
                '研发费用_服务费': 28,
                '研发费用_委外': 29,
                '销售费用_飞机动车等': 30,
                '销售费用_住宿费': 31,
                '销售费用_车辆费': 32,
                '销售费用_市内交通': 33,
                '销售费用_招待公关': 34,
                '销售费用_服务费': 35,
                '销售费用_经销返点': 36,
                '销售费用_其他': 37,
                '管理费用_办公费': 38,
                '管理费用_办公租金物业费水电费': 39,
                '管理费用_市内交通': 40,
                '管理费用_招待公关': 41,
                '管理费用_飞机动车等': 42,
                '管理费用_人员薪资': 43,
                '管理费用_社保公积金': 44,
                '管理费用_员工福利': 45,
                '管理费用_其他': 46,
                '财务费用_手续费': 47,
                '财务费用_结息': 48,
                '财务费用_贷款利息': 49,
                '应缴税金_增值税及附加': 50,
                '应缴税金_所得税': 51,
                '应缴税金_印花税': 52,
                '应缴税金_工资个税': 53,
                '应缴税金_劳务个税': 54,
                '有形资产_办公设备': 55,
                '有形资产_办公家具包含车': 56,
                '营业外支出_违约金': 57,
                '营业外支出_罚款': 58,
            },
            'data': {
                'skip_vouchers': ['期初余额', '本期合计', '本年累计', ''],
                'columns': {
                    'date': '日期', 'voucher': '凭证字号', 'description': '摘要',
                    'contra': '对方科目', 'debit': '借方', 'credit': '贷方',
                    'direction': '方向', 'balance': '余额'
                },
                'header_rows': 4, 'data_start_row': 5,
                'decimal_places': 2, 'validation_threshold': 0.01
            }
        }
    
    def auto_save(self):
        try:
            config = self.build_config()
            config['allow_prefixes'] = ALLOW_PREFIXES
            self.config_manager.save_config(config)
            self.config_obj.reload_classification()
            self.config_obj.data.classification.allow_prefixes = ALLOW_PREFIXES
            self.append_log('💾 配置已自动保存并重新加载')
        except Exception as e:
            logger.error(f"自动保存失败: {e}")
    
    # ==================== 运行 ====================
    def append_log(self, msg):
        self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}')
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        logger.info(msg)
    
    def update_progress(self, value, label):
        self.progress_bar.setValue(value)
        self.progress_label.setText(label)
    
    def run_generator(self):
        """判断当前Tab并运行"""
        current_tab = self.tabs.currentIndex()
        
        if current_tab == 0:
            self._run_single_mode()
        elif current_tab == 1:
            self._run_summary_mode()
        else:
            QMessageBox.warning(self, '提示', '请在"单文件生成"或"汇总模式"Tab中操作')
    
    def _run_single_mode(self):
        """运行单文件生成模式 - 目录模式始终创建新文件"""
        cashflow_input = self.single_cashflow_path.text().strip()
        
        if not cashflow_input:
            QMessageBox.warning(self, '提示', '请选择输出目录或现金流表文件')
            return
        if not self.single_files:
            QMessageBox.warning(self, '提示', '请选择明细账文件（支持Ctrl多选）')
            return
        
        is_valid, errors = self._check_rules()
        if not is_valid:
            error_msg = "支出规则存在语法错误，请修正后重试：\n\n"
            for err in errors:
                error_msg += f"  • {err}\n"
            error_msg += "\n💡 提示：点击「验证规则」按钮可检查语法错误"
            QMessageBox.warning(self, '规则错误', error_msg)
            return
        
        self._save_config()
        
        cashflow_path = Path(cashflow_input)
        
        if cashflow_path.suffix in ['.xlsx', '.xls']:
            # ===== 用户选择了已有文件 =====
            cashflow_file = cashflow_path
            self.append_log(f'📄 使用已有现金流表: {cashflow_file.name}')
            if len(self.single_files) > 1:
                self.append_log(f'📌 将添加 {len(self.single_files)} 个Sheet到现有文件')
        else:
            # ===== 用户选择了目录，始终创建新文件（带时间戳） =====
            dir_path = cashflow_path
            first_name = self.single_files[0].stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"现金流表_{timestamp}.xlsx"
            cashflow_file = dir_path / filename
            self.append_log(f'📂 目录模式，创建新文件: {filename}')
        
        cashflow_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.append_log(f'📄 输出文件: {cashflow_file}')
        self.append_log(f'📁 共 {len(self.single_files)} 个明细账文件待处理')
        self.append_log(f'📌 模式: 追加Sheet到已有文件' if cashflow_path.suffix in ['.xlsx', '.xls'] else '📌 模式: 创建新文件')
        
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText('准备中...')
        
        self.single_worker = WorkerThread(
            self.single_files,
            cashflow_file,
            mode="single"
        )
        self.single_worker.progress_updated.connect(self.update_progress)
        self.single_worker.log_updated.connect(self.append_log)
        self.single_worker.file_progress.connect(self._on_file_progress)
        self.single_worker.finished.connect(lambda success, result: self._on_single_finished(success, result))
        self.single_worker.start()
    
    def _run_summary_mode(self):
        """运行汇总模式 - 目录模式始终创建新文件"""
        cashflow_input = self.summary_cashflow_path.text().strip()
    
        if not cashflow_input:
            QMessageBox.warning(self, '提示', '请选择输出目录或汇总表文件')
            return
        if not self.summary_files:
            QMessageBox.warning(self, '提示', '请选择明细账文件（支持Ctrl多选）')
            return
    
        is_valid, errors = self._check_rules()
        if not is_valid:
            error_msg = "支出规则存在语法错误，请修正后重试：\n\n"
            for err in errors:
                error_msg += f"  • {err}\n"
            error_msg += "\n💡 提示：点击「验证规则」按钮可检查语法错误"
            QMessageBox.warning(self, '规则错误', error_msg)
            return
    
        self._save_config()
    
        cashflow_path = Path(cashflow_input)
    
        if cashflow_path.suffix in ['.xlsx', '.xls']:
            # ===== 用户选择了已有文件 =====
            if not cashflow_path.exists():
                QMessageBox.warning(self, '提示', f'文件不存在: {cashflow_path.name}')
                return
            cashflow_file = cashflow_path
            self.append_log(f'📄 使用已有文件: {cashflow_file.name}')
        else:
            # ===== 用户选择了目录，始终创建新文件（带时间戳） =====
            dir_path = cashflow_path
            first_name = self.summary_files[0].stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"现金流表_{timestamp}.xlsx"
            cashflow_file = dir_path / filename
            self.append_log(f'📂 目录模式，创建新文件: {filename}')
    
        cashflow_file.parent.mkdir(parents=True, exist_ok=True)
    
        self.append_log(f'📊 汇总模式: 共 {len(self.summary_files)} 个文件')
        self.append_log(f'📄 输出文件: {cashflow_file}')
        self.append_log(f'📌 模式: 创建新文件并生成汇总表')
    
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText('准备中...')
    
        self.summary_worker = WorkerThread(
            self.summary_files,
            cashflow_file,
            mode="summary"
        )
        self.summary_worker.progress_updated.connect(self.update_progress)
        self.summary_worker.log_updated.connect(self.append_log)
        self.summary_worker.file_progress.connect(self._on_file_progress)
        self.summary_worker.finished.connect(lambda success, result: self._on_summary_finished(success, result))
        self.summary_worker.start() 
    
    def _on_file_progress(self, current, total, filename):
        self.progress_label.setText(f'[{current}/{total}] {filename}')
    
    def _on_single_finished(self, success, result):
        """单文件生成完成回调"""
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.single_worker = None
        
        if success:
            self.progress_label.setText('✅ 单文件生成完成')
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #059669, stop:1 #10b981);
                    border-radius: 6px;
                }
            """)
            QMessageBox.information(self, '完成', f'单文件生成完成\n\n{result}')
        else:
            self.progress_label.setText('❌ 失败')
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #dc2626, stop:1 #ef4444);
                    border-radius: 6px;
                }
            """)
            if result != '已停止':
                QMessageBox.warning(self, '错误', f'处理失败\n\n{result}')
    
    def _on_summary_finished(self, success, result):
        """汇总模式完成回调"""
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.summary_worker = None
        
        if success:
            self.progress_label.setText('✅ 汇总完成')
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #059669, stop:1 #10b981);
                    border-radius: 6px;
                }
            """)
            QMessageBox.information(self, '完成', f'汇总完成\n\n{result}')
        else:
            self.progress_label.setText('❌ 汇总失败')
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #dc2626, stop:1 #ef4444);
                    border-radius: 6px;
                }
            """)
            if result != '已停止':
                QMessageBox.warning(self, '错误', f'汇总失败\n\n{result}')
    
    def stop_generator(self):
        """停止当前运行的线程"""
        if self.single_worker and self.single_worker.isRunning():
            self.single_worker.stop()
            self.single_worker.wait()
            self.single_worker = None
            self.append_log('⏹ 单文件生成已停止')
        elif self.summary_worker and self.summary_worker.isRunning():
            self.summary_worker.stop()
            self.summary_worker.wait()
            self.summary_worker = None
            self.append_log('⏹ 汇总已停止')
        else:
            return
        
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_label.setText('已停止')
        self.progress_bar.setValue(0)
    
    def _save_config(self):
        """保存配置"""
        config = self.build_config()
        config['allow_prefixes'] = ALLOW_PREFIXES
        self.config_manager.save_config(config)
        self.config_obj.reload_classification()
        self.config_obj.data.classification.allow_prefixes = ALLOW_PREFIXES
        self.append_log('📋 规则已重新加载')
        self._log_rules()
    
    def _check_rules(self):
        text = self.expense_rules.toPlainText()
        errors = []
        lines = text.split('\n')
    
        for i, line in enumerate(lines, 1):
            original_line = line
            line = line.strip()
            if not line:
                continue
        
            if ':' not in line and '：' not in line:
                errors.append(f"第{i}行: 缺少冒号「:」 → \"{original_line}\"")
                continue
        
            if '：' in line:
                errors.append(f"第{i}行: 使用了中文冒号「：」，请改为英文冒号「:」 → \"{original_line}\"")
                continue
        
            parts = line.split(':', 1)
            if len(parts) != 2:
                errors.append(f"第{i}行: 格式错误 → \"{original_line}\"")
                continue
        
            category = parts[0].strip()
            keywords = parts[1].strip()
        
            if not category:
                errors.append(f"第{i}行: 分类名称为空 → \"{original_line}\"")
        
            if not keywords:
                errors.append(f"第{i}行: 关键词为空 → \"{original_line}\"")
        
            if '，' in keywords:
                errors.append(f"第{i}行: 关键词中使用了中文逗号「，」，请改为英文逗号「,」 → \"{original_line}\"")
        
            if ',,' in keywords:
                errors.append(f"第{i}行: 存在连续逗号 → \"{original_line}\"")
        
            if keywords.endswith(','):
                errors.append(f"第{i}行: 关键词末尾有多余逗号 → \"{original_line}\"")
    
        return (len(errors) == 0, errors)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName('现金流量报表生成器')
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()