#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAD处理任务 - Celery异步任务
CAD Processing Tasks - Celery Async Tasks

将CAD处理逻辑封装为异步任务
"""

from celery import current_task
from typing import Dict, Any, List
import structlog
from pathlib import Path
import json

from ..celery_app import celery_app, CADTask, update_progress
from ..cad_processor import CADProcessor, CADProcessingError
from ...database import SessionLocal, Project, ProjectFile, ProcessingTask

logger = structlog.get_logger(__name__)

@celery_app.task(bind=True, base=CADTask, name="cad_tasks.convert_dwg_to_dxf")
def convert_dwg_to_dxf_task(self, project_id: int, file_id: int, dwg_file_path: str, output_dir: str) -> Dict[str, Any]:
    """
    DWG转DXF异步任务
    
    Args:
        project_id: 项目ID
        file_id: 文件ID
        dwg_file_path: DWG文件路径
        output_dir: 输出目录
        
    Returns:
        Dict包含转换结果
    """
    task_id = self.request.id
    logger.info("开始DWG转DXF任务", task_id=task_id, project_id=project_id, file_id=file_id)
    
    try:
        # 更新进度
        update_progress(task_id, 0.1, "初始化CAD处理器")
        
        # 创建CAD处理器
        processor = CADProcessor()
        
        # 更新进度
        update_progress(task_id, 0.2, "开始DWG转换")
        
        # 执行转换 (这里需要在同步上下文中调用异步方法)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(
            processor.convert_dwg_to_dxf(dwg_file_path, output_dir)
        )
        
        # 更新进度
        update_progress(task_id, 0.8, "转换完成，更新数据库")
        
        # 更新数据库
        db = SessionLocal()
        try:
            project_file = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
            if project_file:
                project_file.status = "converted"
                project_file.converted_path = result["output_file"]
                db.commit()
                logger.info("文件状态已更新", file_id=file_id, status="converted")
        finally:
            db.close()
        
        # 更新进度
        update_progress(task_id, 1.0, "DWG转换任务完成")
        
        logger.info("DWG转DXF任务完成", task_id=task_id, result=result)
        return result
        
    except CADProcessingError as e:
        logger.error("CAD处理错误", task_id=task_id, error=str(e))
        # 更新文件状态为失败
        db = SessionLocal()
        try:
            project_file = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
            if project_file:
                project_file.status = "failed"
                db.commit()
        finally:
            db.close()
        raise
    except Exception as e:
        logger.error("DWG转换任务失败", task_id=task_id, error=str(e))
        raise

@celery_app.task(bind=True, base=CADTask, name="cad_tasks.extract_texts_from_dxf")
def extract_texts_from_dxf_task(self, project_id: int, file_id: int, dxf_file_path: str, output_dir: str) -> Dict[str, Any]:
    """
    DXF文本提取异步任务
    
    Args:
        project_id: 项目ID
        file_id: 文件ID
        dxf_file_path: DXF文件路径
        output_dir: 输出目录
        
    Returns:
        Dict包含提取结果
    """
    task_id = self.request.id
    logger.info("开始DXF文本提取任务", task_id=task_id, project_id=project_id, file_id=file_id)
    
    try:
        # 更新进度
        update_progress(task_id, 0.1, "初始化文本提取器")
        
        # 创建CAD处理器
        processor = CADProcessor()
        
        # 更新进度
        update_progress(task_id, 0.2, "开始文本提取")
        
        # 执行提取
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(
            processor.extract_texts_from_dxf(dxf_file_path, output_dir)
        )
        
        # 更新进度
        update_progress(task_id, 0.8, "提取完成，更新数据库")
        
        # 更新数据库
        db = SessionLocal()
        try:
            project_file = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
            if project_file:
                project_file.status = "extracted"
                project_file.excel_path = result["output_file"]
                project_file.extracted_texts_count = result["texts_count"]
                db.commit()
                logger.info("文件状态已更新", file_id=file_id, status="extracted")
        finally:
            db.close()
        
        # 更新进度
        update_progress(task_id, 1.0, "文本提取任务完成")
        
        logger.info("DXF文本提取任务完成", task_id=task_id, result=result)
        return result
        
    except CADProcessingError as e:
        logger.error("CAD处理错误", task_id=task_id, error=str(e))
        # 更新文件状态为失败
        db = SessionLocal()
        try:
            project_file = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
            if project_file:
                project_file.status = "failed"
                db.commit()
        finally:
            db.close()
        raise
    except Exception as e:
        logger.error("文本提取任务失败", task_id=task_id, error=str(e))
        raise

@celery_app.task(bind=True, base=CADTask, name="cad_tasks.apply_translation_to_dxf")
def apply_translation_to_dxf_task(
    self, 
    project_id: int, 
    file_id: int, 
    dxf_file_path: str, 
    excel_file_path: str,
    output_dir: str,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    翻译应用异步任务
    
    Args:
        project_id: 项目ID
        file_id: 文件ID
        dxf_file_path: DXF文件路径
        excel_file_path: Excel翻译文件路径
        output_dir: 输出目录
        config: 翻译配置
        
    Returns:
        Dict包含应用结果
    """
    task_id = self.request.id
    logger.info("开始翻译应用任务", task_id=task_id, project_id=project_id, file_id=file_id)
    
    try:
        # 更新进度
        update_progress(task_id, 0.1, "初始化翻译处理器")
        
        # 创建CAD处理器
        processor = CADProcessor()
        
        # 更新进度
        update_progress(task_id, 0.2, "开始应用翻译")
        
        # 执行翻译应用
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(
            processor.apply_translation_to_dxf(
                dxf_file_path,
                excel_file_path,
                output_dir,
                config.get("font_name", "Times New Roman"),
                config.get("translation_mode", "add"),
                config.get("font_size_reduction", 4)
            )
        )
        
        # 更新进度
        update_progress(task_id, 0.8, "翻译应用完成，更新数据库")
        
        # 更新数据库
        db = SessionLocal()
        try:
            project_file = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
            if project_file:
                project_file.status = "translated"
                project_file.translated_path = result["output_file"]
                project_file.translated_texts_count = result["translation_count"]
                db.commit()
                logger.info("文件状态已更新", file_id=file_id, status="translated")
        finally:
            db.close()
        
        # 更新进度
        update_progress(task_id, 1.0, "翻译应用任务完成")
        
        logger.info("翻译应用任务完成", task_id=task_id, result=result)
        return result
        
    except CADProcessingError as e:
        logger.error("CAD处理错误", task_id=task_id, error=str(e))
        # 更新文件状态为失败
        db = SessionLocal()
        try:
            project_file = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
            if project_file:
                project_file.status = "failed"
                db.commit()
        finally:
            db.close()
        raise
    except Exception as e:
        logger.error("翻译应用任务失败", task_id=task_id, error=str(e))
        raise

@celery_app.task(bind=True, base=CADTask, name="cad_tasks.process_project_batch")
def process_project_batch_task(self, project_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    批量处理项目文件异步任务 - 一键处理功能
    
    Args:
        project_id: 项目ID
        config: 处理配置
        
    Returns:
        Dict包含批量处理结果
    """
    task_id = self.request.id
    logger.info("开始批量处理项目任务", task_id=task_id, project_id=project_id)
    
    try:
        # 更新进度
        update_progress(task_id, 0.05, "获取项目文件列表")
        
        # 获取项目文件
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError(f"项目不存在: {project_id}")
            
            files = db.query(ProjectFile).filter(ProjectFile.project_id == project_id).all()
            if not files:
                raise ValueError(f"项目中没有文件: {project_id}")
            
            file_paths = [f.file_path for f in files]
            
        finally:
            db.close()
        
        # 更新进度
        update_progress(task_id, 0.1, f"开始处理 {len(file_paths)} 个文件")
        
        # 创建CAD处理器
        processor = CADProcessor()
        
        # 执行批量处理
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(
            processor.process_project_files(project_id, file_paths, config)
        )
        
        # 更新进度
        update_progress(task_id, 0.9, "批量处理完成，更新项目状态")
        
        # 更新项目状态
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.status = "completed" if result["failed_files"] == 0 else "partially_completed"
                project.processed_files = result["converted_files"]
                db.commit()
                logger.info("项目状态已更新", project_id=project_id, status=project.status)
        finally:
            db.close()
        
        # 更新进度
        update_progress(task_id, 1.0, "批量处理任务完成")
        
        logger.info("批量处理项目任务完成", task_id=task_id, result=result)
        return result
        
    except Exception as e:
        logger.error("批量处理项目任务失败", task_id=task_id, error=str(e))
        # 更新项目状态为失败
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.status = "failed"
                db.commit()
        finally:
            db.close()
        raise