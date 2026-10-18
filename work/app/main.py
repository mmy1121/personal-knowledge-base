"""V0.1 FastAPI 后端：文本录入 / TXT·MD 上传 / 关键词检索 / 列表 / 详情 / 删除。

统一响应格式：{"code": 200, "msg": "success", "data": {...}}
数据先行：入库只依赖 SQLite，不依赖任何 LLM / 向量服务。
"""
import os
from typing import Optional

from charset_normalizer import from_bytes
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import config  # noqa: F401  必须最先导入：加载 .env 到环境变量
from . import db, parsers

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "kb.db"))
# 安全默认：只放行本机来源；悬浮框是原生客户端，不依赖 CORS
CORS_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if o]
MAX_UPLOAD = 5 * 1024 * 1024  # 5MB 上传上限
ALLOWED_SOURCE = {"paste", "float_window", "file"}

app = FastAPI(title="个人知识库", version="0.1.0")
@app.middleware("http")
async def _local_guard(request, call_next):
    """本地 API 防护：
    - Host 头必须是本机（防 DNS rebinding）；
    - 若设置了环境变量 KB_API_TOKEN，则除 OPTIONS 与 /health 外必须携带 X-KB-Token。
    默认不设 token（开箱即用），设置后悬浮框通过同名环境变量携带。
    """
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host not in ("127.0.0.1", "localhost", "testserver", "[::1]", ""):
        return JSONResponse({"code": 403, "msg": "非法 Host", "data": {}}, status_code=403)
    token = os.environ.get("KB_API_TOKEN", "")
    if token and request.method != "OPTIONS" and request.url.path != "/api/v1/health":
        import hmac  # 常量时间比较，避免时序侧信道
        if not hmac.compare_digest(request.headers.get("x-kb-token", "").encode("utf-8"),
                                   token.encode("utf-8")):
            return JSONResponse({"code": 401, "msg": "缺少或错误的 X-KB-Token", "data": {}},
                                status_code=401)
    return await call_next(request)


app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


def ok(data=None, msg: str = "success"):
    return {"code": 200, "msg": msg, "data": data if data is not None else {}}


@app.exception_handler(HTTPException)
async def _http_exc(_, exc: HTTPException):
    return JSONResponse({"code": exc.status_code, "msg": str(exc.detail), "data": {}},
                        status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _val_exc(_, exc: RequestValidationError):
    return JSONResponse({"code": 422, "msg": "请求参数错误", "data": {"errors": exc.errors()}},
                        status_code=422)


class TextIn(BaseModel):
    text: str
    title: Optional[str] = None
    source_type: Optional[str] = "paste"


@app.get("/api/v1/health")
def health():
    """健康检查：除存活外，报告 LLM / Embedding / 向量库配置与库内计数，便于排障。"""
    info = {"status": "up", "version": app.version,
            "llm_provider": os.environ.get("LLM_PROVIDER", "mock"),
            "embedding_mode": os.environ.get("EMBEDDING_MODE", "mock"),
            "vector_store": "float16-blob+numpy", "auto_process": os.environ.get("AUTO_PROCESS", "1") != "0"}
    try:
        with db.session(DB_PATH) as conn:
            info["documents"] = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            info["chunks"] = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            by = conn.execute("SELECT status, COUNT(*) c FROM documents GROUP BY status").fetchall()
            info["by_status"] = {r[0]: r[1] for r in by}
    except Exception as e:
        info["db_error"] = str(e)
    return ok(info)


def _auto_process(background: BackgroundTasks, doc_id: int) -> None:
    """入库后异步触发 摘要->标签->向量化->分类。
    数据先行：此时正文与 FTS 已提交，处理失败只改 status，不影响入库。
    AUTO_PROCESS=0 可关闭（测试 pending 状态用）。"""
    if os.environ.get("AUTO_PROCESS", "1") == "0":
        return
    from . import pipeline
    background.add_task(pipeline.process_by_id, DB_PATH, doc_id)


@app.post("/api/v1/documents/text")
def add_text(body: TextIn, background: BackgroundTasks):
    st = body.source_type if body.source_type in ALLOWED_SOURCE else "paste"
    try:
        with db.session(DB_PATH) as conn:
            # 先查重再入库：重复内容不覆盖已有文档（保护用户手工修正的分类/标签），仅告知
            dup = db.find_duplicate(conn, body.text)
            doc_id = db.add_document(conn, body.text, body.title, st)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _auto_process(background, doc_id)
    return ok({"doc_id": doc_id, "status": "pending", "duplicate_of": dup})


def decode_bytes(raw: bytes) -> str:
    """自动识别 UTF-8 / GBK / GB18030 等编码。"""
    best = from_bytes(raw).best()
    if best is None:
        raise ValueError("无法识别文件编码")
    return str(best)


@app.post("/api/v1/documents/upload")
async def upload(background: BackgroundTasks, file: UploadFile = File(...)):
    name = file.filename or "未命名"
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "文件超过 5MB 上限")
    try:
        # V0.2：5 种格式统一走 parsers；解析失败抛 ParseError(ValueError)，不存空内容
        title, text = parsers.parse_file(name, raw)
        with db.session(DB_PATH) as conn:
            dup = db.find_duplicate(conn, text)  # 重复仅告知，不覆盖已有文档
            doc_id = db.add_document(conn, text, title, "file")
    except ValueError as e:
        raise HTTPException(400, str(e))
    _auto_process(background, doc_id)
    return ok({"doc_id": doc_id, "status": "pending", "title": title,
               "duplicate_of": dup, "char_count": len(text),
               "needs_chunking": len(text) > parsers.CHUNK_THRESHOLD})


@app.post("/api/v1/search")
def search(body: dict):
    q = (body.get("query") or "").strip()
    if not q:
        raise HTTPException(400, "query 不能为空")
    limit = int(body.get("limit", 10))
    filters = body.get("filters") or {}
    from . import hybrid
    with db.session(DB_PATH) as conn:
        # V0.4：关键词 + 语义 -> RRF；未配向量或向量路异常时自动退化为纯关键词
        results = hybrid.hybrid_search(
            conn, q, limit,
            source_type=filters.get("source_type"),
            time_from=filters.get("time_from"),
            time_to=filters.get("time_to"),
            category_path=filters.get("category_path"),
            tag=filters.get("tag"))
        return ok({"results": results})


@app.get("/api/v1/documents")
def list_docs(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
              source_type: Optional[str] = None, category_path: Optional[str] = None,
              tag: Optional[str] = None, time_from: Optional[float] = None,
              time_to: Optional[float] = None, status: Optional[str] = None):
    """只查元数据，不加载正文全文。支持按来源/分类(含子分类)/标签/时间/状态筛选。"""
    conds, args = [], []
    if source_type:
        conds.append("source_type=?"); args.append(source_type)
    if status:
        conds.append("status=?"); args.append(status)
    if category_path:
        cp = category_path.strip("/")
        conds.append("(category_path=? OR category_path LIKE ?)"); args += [cp, cp + "/%"]
    if tag:
        conds.append("id IN (SELECT dt.doc_id FROM document_tags dt JOIN tags t ON t.id=dt.tag_id WHERE t.name=?)")
        args.append(tag)
    if time_from is not None:
        conds.append("created_at>=?"); args.append(time_from)
    if time_to is not None:
        conds.append("created_at<=?"); args.append(time_to)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    with db.session(DB_PATH) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM documents {where}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT id,title,source_type,status,char_count,summary,category_path,tags,created_at "
            f"FROM documents {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            args + [size, (page - 1) * size]).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
        items.append(d)
    return ok({"total": total, "page": page, "size": size, "items": items})


@app.get("/api/v1/documents/{doc_id}")
def get_doc(doc_id: int):
    with db.session(DB_PATH) as conn:
        r = conn.execute(
            "SELECT d.*, b.clean_text FROM documents d JOIN document_bodies b ON b.doc_id=d.id "
            "WHERE d.id=?", (doc_id,)).fetchone()
    if not r:
        raise HTTPException(404, "文档不存在")
    return ok(dict(r))


@app.post("/api/v1/documents/{doc_id}/reprocess")
def reprocess_doc(doc_id: int):
    """失败重试：重新处理 failed / pending / processing 的文档，只重做缺失步骤。"""
    from . import pipeline
    with db.session(DB_PATH) as conn:
        if not conn.execute("SELECT 1 FROM documents WHERE id=?", (doc_id,)).fetchone():
            raise HTTPException(404, "文档不存在")
        status = pipeline.process_document(conn, doc_id)
        err = conn.execute("SELECT error_message FROM documents WHERE id=?", (doc_id,)).fetchone()[0]
    return ok({"doc_id": doc_id, "status": status, "error_message": err})


@app.on_event("startup")
def _recover_on_startup():
    """进程重启恢复：重新投递 pending/processing 遗留文档。"""
    from . import pipeline
    try:
        pipeline.recover(DB_PATH)
    except Exception as e:  # 恢复失败不阻止服务启动
        print(f"[startup] 恢复遗留文档失败: {e}")


@app.delete("/api/v1/documents/{doc_id}")
def delete_doc(doc_id: int):
    """V0.6：级联删除（切片/向量/FTS/标签关联），并回退分类与标签计数。"""
    from . import manage
    with db.session(DB_PATH) as conn:
        if not manage.delete_document_full(conn, doc_id):
            raise HTTPException(404, "文档不存在")
    return ok({"deleted": doc_id})


class DocPatch(BaseModel):
    title: Optional[str] = None
    category_path: Optional[str] = None
    tags: Optional[list[str]] = None


@app.patch("/api/v1/documents/{doc_id}")
def patch_doc(doc_id: int, body: DocPatch):
    """更新标题/分类/标签；分类或标签变更记入 corrections。"""
    from . import classify, manage
    try:
        with db.session(DB_PATH) as conn:
            r = manage.update_document(conn, doc_id, body.title, body.category_path, body.tags)
    except (ValueError, classify.CategoryLimitError) as e:
        raise HTTPException(400, str(e))
    if r is None:
        raise HTTPException(404, "文档不存在")
    return ok(r)


@app.get("/", include_in_schema=False)
def index_page():
    """最小管理页：由后端直接提供静态 HTML。"""
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if not os.path.exists(path):
        raise HTTPException(404, "管理页不存在")
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.get("/api/v1/tags")
def list_tags():
    with db.session(DB_PATH) as conn:
        rows = conn.execute("SELECT id, name, doc_count FROM tags WHERE doc_count>0 "
                            "ORDER BY doc_count DESC, name").fetchall()
    return ok({"items": [dict(r) for r in rows]})


@app.get("/api/v1/categories")
def get_categories():
    from . import manage
    with db.session(DB_PATH) as conn:
        return ok({"tree": manage.category_tree(conn)})


class CatIn(BaseModel):
    path: str
    description: Optional[str] = ""


@app.post("/api/v1/categories")
def add_category(body: CatIn):
    from . import classify
    try:
        with db.session(DB_PATH) as conn:
            cid = classify.create_category(conn, body.path, body.description or "")
    except (ValueError, classify.CategoryLimitError) as e:
        raise HTTPException(400, str(e))
    return ok({"id": cid, "path": body.path})


class CatPatch(BaseModel):
    name: Optional[str] = None
    merge_into: Optional[int] = None


@app.patch("/api/v1/categories/{cat_id}")
def patch_category(cat_id: int, body: CatPatch):
    from . import classify, manage
    try:
        with db.session(DB_PATH) as conn:
            if body.merge_into is not None:
                r = manage.merge_category(conn, cat_id, body.merge_into)
            elif body.name is not None:
                r = manage.rename_category(conn, cat_id, body.name)
            else:
                raise ValueError("需提供 name 或 merge_into")
    except (ValueError, classify.CategoryLimitError) as e:
        raise HTTPException(400, str(e))
    if r is None:
        raise HTTPException(404, "分类不存在")
    return ok(r)


@app.delete("/api/v1/categories/{cat_id}")
def delete_category_api(cat_id: int, migrate_to: Optional[int] = None):
    """删除分类：有文档时必须指定 migrate_to 迁移目标，否则返回 400 并给出警告。"""
    from . import classify, manage
    try:
        with db.session(DB_PATH) as conn:
            r = manage.delete_category(conn, cat_id, migrate_to)
    except (ValueError, classify.CategoryLimitError) as e:
        raise HTTPException(400, str(e))
    if r is None:
        raise HTTPException(404, "分类不存在")
    return ok(r)
