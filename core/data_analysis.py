"""Data Analysis — CSV/Excel analysis + chart generation."""

import io
import json
import logging
import os
import uuid

from core import model_router
from core.config import config

logger = logging.getLogger(__name__)

CHARTS_DIR = os.path.join("data", "charts")


def _ensure_charts_dir() -> str:
    os.makedirs(CHARTS_DIR, exist_ok=True)
    return CHARTS_DIR


class DataAnalyst:
    def __init__(self):
        pass

    # ── Loaders ───────────────────────────────────────────────────────────────

    def load_csv(self, data: bytes, filename: str = "data.csv") -> "DataAnalyst._Dataset":
        import csv
        text = data.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        columns = reader.fieldnames or []
        return self._Dataset(filename, columns, rows)

    def load_excel(self, data: bytes, filename: str = "data.xlsx") -> "DataAnalyst._Dataset":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            ws = wb.active
            rows_iter = iter(ws.iter_rows(values_only=True))
            headers = [str(h) for h in next(rows_iter, [])]
            rows = [dict(zip(headers, row)) for row in rows_iter]
            return self._Dataset(filename, headers, rows)
        except ImportError:
            raise RuntimeError("openpyxl not installed. pip install openpyxl")

    def load_file(self, file) -> "DataAnalyst._Dataset":
        data = file.read()
        name = file.filename.lower()
        if name.endswith(".csv"):
            return self.load_csv(data, file.filename)
        if name.endswith((".xlsx", ".xls")):
            return self.load_excel(data, file.filename)
        raise ValueError(f"Unsupported format: {name}. Use CSV or Excel.")

    # ── Dataset ───────────────────────────────────────────────────────────────

    class _Dataset:
        def __init__(self, name: str, columns: list, rows: list[dict]):
            self.name = name
            self.columns = list(columns)
            self.rows = rows

        def summary(self) -> str:
            lines = [
                f"**Dataset:** {self.name}",
                f"**Rows:** {len(self.rows)} | **Columns:** {len(self.columns)}",
                f"**Columns:** {', '.join(str(c) for c in self.columns)}",
            ]
            # Numeric stats
            for col in self.columns:
                vals = []
                for r in self.rows:
                    v = r.get(col)
                    try:
                        vals.append(float(v))
                    except (TypeError, ValueError):
                        pass
                if vals:
                    lines.append(
                        f"  `{col}`: min={min(vals):.2f}, max={max(vals):.2f}, "
                        f"avg={sum(vals)/len(vals):.2f}, count={len(vals)}"
                    )
            # Sample rows
            lines.append("\n**Sample (first 3 rows):**")
            for row in self.rows[:3]:
                lines.append(str({k: row.get(k) for k in self.columns[:6]}))
            return "\n".join(lines)

        def to_csv_text(self, limit: int = 200) -> str:
            import csv, io
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=self.columns)
            w.writeheader()
            w.writerows(self.rows[:limit])
            return buf.getvalue()

    # ── AI Analysis ───────────────────────────────────────────────────────────

    def analyze(self, dataset: "_Dataset", question: str = "") -> str:
        prompt_q = question or "Provide a comprehensive analysis of this dataset."
        context = dataset.summary() + "\n\n**CSV sample:**\n" + dataset.to_csv_text(50)

        result = model_router.chat(
            [{"role": "user", "content": f"Dataset info:\n{context}\n\nQuestion: {prompt_q}"}],
            system="You are an expert data analyst. Analyze the provided dataset and answer the question clearly. Use markdown formatting.",
            max_tokens=4096,
        )
        return result if isinstance(result, str) else "".join(result)

    # ── Chart Generation ──────────────────────────────────────────────────────

    def generate_chart(self, dataset: "_Dataset", chart_type: str = "auto",
                       x_col: str = "", y_col: str = "", title: str = "") -> dict:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return {"error": "matplotlib not installed. pip install matplotlib"}

        rows = dataset.rows
        cols = dataset.columns

        # Auto-detect numeric columns
        num_cols = []
        for c in cols:
            try:
                float(rows[0].get(c, "x"))
                num_cols.append(c)
            except (ValueError, TypeError, IndexError):
                pass

        cat_cols = [c for c in cols if c not in num_cols]

        x = x_col or (cat_cols[0] if cat_cols else (cols[0] if cols else ""))
        y = y_col or (num_cols[0] if num_cols else (cols[1] if len(cols) > 1 else ""))

        if not x or not y:
            return {"error": "Could not determine X and Y columns automatically."}

        xs = [str(r.get(x, "")) for r in rows[:50]]
        try:
            ys = [float(r.get(y, 0) or 0) for r in rows[:50]]
        except ValueError:
            return {"error": f"Column '{y}' is not numeric."}

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "bar" or (chart_type == "auto" and len(xs) <= 20):
            ax.bar(xs, ys, color="#6c63ff")
            ax.set_xticklabels(xs, rotation=45, ha="right", fontsize=8)
        elif chart_type == "line" or chart_type == "auto":
            ax.plot(xs, ys, marker="o", color="#6c63ff", linewidth=2)
            ax.set_xticklabels(xs, rotation=45, ha="right", fontsize=8)
        elif chart_type == "pie" and len(xs) <= 10:
            ax.pie(ys, labels=xs, autopct="%1.1f%%")
        elif chart_type == "scatter":
            ax.scatter(xs, ys, color="#6c63ff", alpha=0.7)
        else:
            ax.bar(xs, ys, color="#6c63ff")

        ax.set_title(title or f"{y} by {x}", fontsize=14, fontweight="bold")
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()

        chart_id = uuid.uuid4().hex[:10]
        path = os.path.join(_ensure_charts_dir(), f"chart_{chart_id}.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return {"chart_id": chart_id, "path": path, "url": f"/api/charts/{chart_id}"}
