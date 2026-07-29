#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
翻译相关的Celery异步任务
Translation Related Celery Tasks
"""

import os
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
import structlog

from app.services.celery_app import celery_app
from app.services.alibaba_ai_translation_service import alibaba_ai_excel_processor as ai_excel_processor
from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

@celery_app.task(bind=True, name="translate_excel_task")
def translate_excel_task(
    self,
    input_file_path: str,
    text_columns: Optional[List[str]] = None,
    source_lang: str = "auto",
    target_lang: str = "zh",
    translation_mode: str = "add"
) -> Dict[str, Any]:
    """
    异步翻译Excel文件任务
    
    Args:
        self: Celery任务实例
        input_file_path: 输入文件路径
        text_columns: 需要翻译的列名列表
        source_lang: 源语言
        target_lang: 目标语言
        translation_mode: 翻译模式
    
    Returns:
        翻译结果字典
    """
    try:
        logger.info("开始异步Excel翻译任务", 
                   task_id=self.request.id, 
                   input_file=input_file_path)
        
        # 更新任务状态为进行中
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 100,
                'status': '正在准备翻译...'
            }
        )
        
        # 验证输入文件
        if not os.path.exists(input_file_path):
            raise FileNotFoundError(f"输入文件不存在: {input_file_path}")
        
        # 生成输出文件路径
        input_path = Path(input_file_path)
        output_filename = f"translated_{input_path.name}"
        output_path = settings.get_output_path() / output_filename
        
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 更新进度
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 10,
                'total': 100,
                'status': '正在分析Excel文件...'
            }
        )
        
        # 执行翻译
        start_time = time.time()
        
        try:
            stats = ai_excel_processor.translate_excel_file(
                input_file_path=input_file_path,
                output_file_path=str(output_path),
                text_columns=text_columns,
                source_lang=source_lang,
                target_lang=target_lang,
                translation_mode=translation_mode
            )
            
            # 更新进度
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': 80,
                    'total': 100,
                    'status': '正在生成翻译报告...'
                }
            )
            
            # 创建翻译报告
            report_path = ai_excel_processor.create_translation_report(stats, str(output_path))
            
            processing_time = time.time() - start_time
            
            # 清理输入文件（如果是临时文件）
            if input_path.parent.name == "uploads":
                try:
                    os.unlink(input_file_path)
                    logger.info("已清理临时输入文件", file=input_file_path)
                except Exception as e:
                    logger.warning("清理临时文件失败", file=input_file_path, error=str(e))
            
            # 返回成功结果
            result = {
                'success': True,
                'message': 'Excel翻译完成',
                'output_filename': output_filename,
                'download_url': f'/api/translation/download/{output_filename}',
                'report_filename': os.path.basename(report_path) if report_path else None,
                'processing_time': round(processing_time, 2),
                'stats': stats
            }
            
            logger.info("Excel翻译任务完成", 
                       task_id=self.request.id, 
                       processing_time=processing_time,
                       stats=stats)
            
            return result
            
        except Exception as e:
            logger.error("Excel翻译处理失败", 
                        task_id=self.request.id, 
                        error=str(e))
            raise
            
    except Exception as e:
        logger.error("Excel翻译任务失败", 
                    task_id=self.request.id, 
                    error=str(e))
        
        # 返回失败结果
        return {
            'success': False,
            'message': f'翻译失败: {str(e)}',
            'error': str(e)
        }

@celery_app.task(bind=True, name="batch_translate_task")
def batch_translate_task(
    self,
    texts: List[str],
    source_lang: str = "auto",
    target_lang: str = "zh"
) -> Dict[str, Any]:
    """
    异步批量翻译任务
    
    Args:
        self: Celery任务实例
        texts: 要翻译的文本列表
        source_lang: 源语言
        target_lang: 目标语言
    
    Returns:
        翻译结果字典
    """
    try:
        logger.info("开始异步批量翻译任务", 
                   task_id=self.request.id, 
                   count=len(texts))
        
        from app.services.alibaba_ai_translation_service import alibaba_ai_translation_service as ai_translation_service
        
        total_texts = len(texts)
        translated_texts = []
        
        # 分批处理，避免单次请求过大
        batch_size = 20
        for i in range(0, total_texts, batch_size):
            batch_texts = texts[i:i + batch_size]
            
            # 更新进度
            progress = int((i / total_texts) * 100)
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': progress,
                    'total': 100,
                    'status': f'正在翻译第 {i+1}-{min(i+batch_size, total_texts)} 项...'
                }
            )
            
            # 翻译当前批次
            batch_results = ai_translation_service.translate_batch(
                texts=batch_texts,
                source_lang=source_lang,
                target_lang=target_lang
            )
            
            translated_texts.extend(batch_results)
            
            # 短暂休息，避免API限流
            time.sleep(0.1)
        
        # 统计翻译结果
        successful_translations = sum(
            1 for original, translated in zip(texts, translated_texts)
            if not str(translated).startswith("[translation_error]") and (translated != original or not original.strip())
        )
        
        result = {
            'success': True,
            'message': '批量翻译完成',
            'total_texts': total_texts,
            'successful_translations': successful_translations,
            'failed_translations': total_texts - successful_translations,
            'translated_texts': translated_texts
        }
        
        logger.info("批量翻译任务完成", 
                   task_id=self.request.id, 
                   stats=result)
        
        return result
        
    except Exception as e:
        logger.error("批量翻译任务失败", 
                    task_id=self.request.id, 
                    error=str(e))
        
        return {
            'success': False,
            'message': f'批量翻译失败: {str(e)}',
            'error': str(e)
        }

@celery_app.task(bind=True, name="cad_file_translate_task")
def cad_file_translate_task(
    self,
    project_id: int,
    file_paths: List[str],
    translation_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    CAD文件翻译任务（完整流程）
    
    Args:
        self: Celery任务实例
        project_id: 项目ID
        file_paths: CAD文件路径列表
        translation_config: 翻译配置
    
    Returns:
        处理结果字典
    """
    try:
        logger.info("开始CAD文件翻译任务", 
                   task_id=self.request.id, 
                   project_id=project_id,
                   file_count=len(file_paths))
        
        from app.services.cad_processor import CADProcessor
        
        processor = CADProcessor()
        total_files = len(file_paths)
        processed_files = []
        
        for i, file_path in enumerate(file_paths):
            # 更新进度
            progress = int((i / total_files) * 100)
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': progress,
                    'total': 100,
                    'status': f'正在处理文件 {i+1}/{total_files}: {os.path.basename(file_path)}'
                }
            )
            
            try:
                # 处理单个CAD文件
                result = processor.process_cad_file(
                    file_path=file_path,
                    project_id=project_id,
                    **translation_config
                )
                
                processed_files.append({
                    'file_path': file_path,
                    'success': True,
                    'result': result
                })
                
            except Exception as e:
                logger.error("CAD文件处理失败", 
                           file=file_path, 
                           error=str(e))
                
                processed_files.append({
                    'file_path': file_path,
                    'success': False,
                    'error': str(e)
                })
        
        # 统计结果
        successful_files = sum(1 for f in processed_files if f['success'])
        failed_files = total_files - successful_files
        
        result = {
            'success': True,
            'message': 'CAD文件翻译任务完成',
            'project_id': project_id,
            'total_files': total_files,
            'successful_files': successful_files,
            'failed_files': failed_files,
            'processed_files': processed_files
        }
        
        logger.info("CAD文件翻译任务完成", 
                   task_id=self.request.id, 
                   stats=result)
        
        return result
        
    except Exception as e:
        logger.error("CAD文件翻译任务失败", 
                    task_id=self.request.id, 
                    error=str(e))
        
        return {
            'success': False,
            'message': f'CAD文件翻译失败: {str(e)}',
            'error': str(e)
        }

@celery_app.task(name="cleanup_temp_files")
def cleanup_temp_files():
    """
    清理临时文件任务
    """
    try:
        logger.info("开始清理临时文件")
        
        # 清理上传目录中的旧文件（超过24小时）
        upload_dir = settings.get_upload_path()
        current_time = time.time()
        cleanup_count = 0
        
        for file_path in upload_dir.glob("*"):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > 86400:  # 24小时
                    try:
                        file_path.unlink()
                        cleanup_count += 1
                        logger.debug("已清理临时文件", file=str(file_path))
                    except Exception as e:
                        logger.warning("清理文件失败", file=str(file_path), error=str(e))
        
        logger.info("临时文件清理完成", cleanup_count=cleanup_count)
        return {"cleanup_count": cleanup_count}
        
    except Exception as e:
        logger.error("临时文件清理失败", error=str(e))
        return {"error": str(e)}