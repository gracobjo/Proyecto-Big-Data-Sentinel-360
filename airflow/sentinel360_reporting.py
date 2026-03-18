from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Sentinel360ReportConfig:
    project_dir: str
    reports_subdir: str = "reports/airflow"

    def base_dir(self) -> Path:
        return Path(self.project_dir) / self.reports_subdir


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_dag_run_report(*, config: Sentinel360ReportConfig, context: dict[str, Any]) -> str:
    """
    Genera un reporte Markdown (y un JSON simple) con el estado de la ejecución del DAG.

    Diseñado para ejecutarse como última tarea de un DAG (PythonOperator con provide_context).
    Devuelve la ruta del Markdown generado (string) para que aparezca en XCom/logs.
    """
    dag = context.get("dag")
    dag_run = context.get("dag_run")
    ti = context.get("ti")

    dag_id = getattr(dag, "dag_id", "unknown_dag")
    run_id = getattr(dag_run, "run_id", "unknown_run")
    logical_date = getattr(dag_run, "logical_date", None)
    start_date = getattr(dag_run, "start_date", None)
    end_date = getattr(dag_run, "end_date", None)
    state = getattr(dag_run, "state", None)

    task_instances = []
    if dag_run is not None:
        try:
            task_instances = dag_run.get_task_instances()
        except Exception:
            task_instances = []

    def _fmt_dt(dt: Any) -> str:
        if not dt:
            return ""
        try:
            return dt.isoformat(timespec="seconds")
        except Exception:
            return str(dt)

    base_dir = config.base_dir() / dag_id
    base_dir.mkdir(parents=True, exist_ok=True)

    safe_run_id = run_id.replace(":", "_").replace("/", "_")
    stamp = _utc_now_iso().replace(":", "").replace("+", "_").replace("-", "")
    md_path = base_dir / f"{safe_run_id}_{stamp}.md"
    json_path = base_dir / f"{safe_run_id}_{stamp}.json"
    latest_path = base_dir / "LATEST.md"

    lines = []
    lines.append(f"# Sentinel360 – Reporte de ejecución Airflow")
    lines.append("")
    lines.append(f"- **DAG**: `{dag_id}`")
    lines.append(f"- **run_id**: `{run_id}`")
    if logical_date:
        lines.append(f"- **logical_date**: `{_fmt_dt(logical_date)}`")
    lines.append(f"- **start_date**: `{_fmt_dt(start_date)}`")
    lines.append(f"- **end_date**: `{_fmt_dt(end_date)}`")
    lines.append(f"- **state**: `{state}`")
    lines.append("")
    lines.append("## Tareas")
    lines.append("")
    lines.append("| task_id | state | try_number | start_date | end_date |")
    lines.append("|---|---:|---:|---|---|")

    tasks_json = []
    for inst in task_instances:
        task_id = getattr(inst, "task_id", "")
        inst_state = getattr(inst, "state", "")
        try_number = getattr(inst, "try_number", 0)
        inst_start = getattr(inst, "start_date", None)
        inst_end = getattr(inst, "end_date", None)
        lines.append(
            f"| `{task_id}` | `{inst_state}` | `{try_number}` | `{_fmt_dt(inst_start)}` | `{_fmt_dt(inst_end)}` |"
        )
        tasks_json.append(
            {
                "task_id": task_id,
                "state": inst_state,
                "try_number": try_number,
                "start_date": _fmt_dt(inst_start),
                "end_date": _fmt_dt(inst_end),
            }
        )

    lines.append("")
    lines.append("## Evidencias")
    lines.append("")
    lines.append("- Los **logs** detallados están disponibles en la UI de Airflow (por tarea).")
    lines.append(
        "- Este reporte se guarda en el filesystem para poder adjuntarlo en la memoria/defensa."
    )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = {
        "generated_at_utc": _utc_now_iso(),
        "dag_id": dag_id,
        "run_id": run_id,
        "logical_date": _fmt_dt(logical_date),
        "start_date": _fmt_dt(start_date),
        "end_date": _fmt_dt(end_date),
        "state": state,
        "tasks": tasks_json,
    }
    try:
        import json

        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        # Si json no estuviera disponible por cualquier motivo, no bloqueamos el DAG.
        pass

    # Enlace "estable" al último reporte, útil para mostrar en la UI del proyecto
    try:
        latest_path.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass

    if ti is not None:
        try:
            ti.xcom_push(key="sentinel360_report_md_path", value=str(md_path))
        except Exception:
            pass

    return str(md_path)

