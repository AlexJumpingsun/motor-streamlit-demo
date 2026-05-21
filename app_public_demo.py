from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


MAX_POINTS = 120
DEFAULT_REFRESH_SECONDS = 0.8
RPM_NORM_BASE = 300.0


def zh(text: str) -> str:
    return text.encode("ascii").decode("unicode_escape")


def rerun_page() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    st.experimental_rerun()


def to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_setting(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            value = st.secrets[name]
            if value is not None:
                return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


def normalize_sample(raw: dict, source: str) -> dict:
    rpm = to_float(raw.get("rpm", raw.get("rpm_norm", 0.0)))
    rpm_norm = to_float(raw.get("rpm_norm", rpm / RPM_NORM_BASE if rpm else 0.0))
    return {
        "timestamp": raw.get("timestamp") or datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "source": source,
        "ax": to_float(raw.get("ax")),
        "ay": to_float(raw.get("ay")),
        "az": to_float(raw.get("az")),
        "current": to_float(raw.get("current")),
        "rpm": rpm,
        "rpm_norm": max(0.0, min(1.5, rpm_norm)),
        "status": str(raw.get("status") or "WAITING"),
    }


def init_state() -> None:
    if "history" not in st.session_state:
        st.session_state.history = []
    if "last_error" not in st.session_state:
        st.session_state.last_error = ""
    if "demo_tick" not in st.session_state:
        st.session_state.demo_tick = 0
    if "source_key" not in st.session_state:
        st.session_state.source_key = ""


def append_sample(sample: dict | None) -> None:
    if not sample:
        return
    st.session_state.history.append(sample)
    st.session_state.history = st.session_state.history[-MAX_POINTS:]


def reset_history_if_source_changed(source_key: str) -> None:
    if st.session_state.source_key != source_key:
        st.session_state.history = []
        st.session_state.source_key = source_key


def extract_shadow_properties(payload: dict, service_id: str) -> dict | None:
    shadow = payload.get("shadow") or payload.get("device_shadow") or payload.get("services") or []
    if isinstance(shadow, dict):
        shadow = shadow.get("services", [])

    for service in shadow:
        if not isinstance(service, dict):
            continue
        sid = service.get("service_id") or service.get("serviceId")
        if service_id and sid and sid != service_id:
            continue
        reported = service.get("reported") or {}
        properties = reported.get("properties") if isinstance(reported, dict) else None
        properties = properties or service.get("properties")
        if isinstance(properties, dict):
            return properties
    return None


def load_huawei_settings() -> dict:
    return {
        "endpoint": read_setting("HUAWEI_IOTDA_ENDPOINT", ""),
        "project_id": read_setting("HUAWEI_PROJECT_ID", ""),
        "device_id": read_setting("HUAWEI_DEVICE_ID", ""),
        "token": read_setting("HUAWEI_IAM_TOKEN", ""),
        "service_id": read_setting("HUAWEI_SERVICE_ID", "Motor"),
    }


def read_huawei_shadow_sample(settings: dict) -> tuple[dict | None, str]:
    required = ["endpoint", "project_id", "device_id", "token"]
    if any(not settings[name] for name in required):
        return None, zh(r"\u672a\u914d\u7f6e\u534e\u4e3a\u4e91 secrets\uff0c\u5f53\u524d\u81ea\u52a8\u5207\u6362\u4e3a\u5916\u7f51\u6f14\u793a\u6570\u636e\u3002")

    url = (
        f"https://{settings['endpoint'].rstrip('/')}/v5/iot/"
        f"{settings['project_id']}/devices/{settings['device_id']}/shadow"
    )
    request = urllib.request.Request(url, headers={"X-Auth-Token": settings["token"]})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, f"IoTDA shadow read failed: {exc}"

    properties = extract_shadow_properties(payload, settings["service_id"])
    if not properties:
        return None, zh(r"\u5df2\u8fde\u63a5 IoTDA\uff0c\u4f46\u6ca1\u6709\u8bfb\u5230 reported properties\uff0c\u5f53\u524d\u81ea\u52a8\u5207\u6362\u4e3a\u6f14\u793a\u6570\u636e\u3002")

    return normalize_sample(properties, "Huawei IoTDA"), ""


def build_demo_sample(step: int) -> dict:
    phase = step / 6.0
    ax = 0.42 * math.sin(phase)
    ay = 0.37 * math.sin(phase + 1.2)
    az = 0.48 * math.sin(phase + 2.1)
    current = 0.34 + 0.09 * math.sin(phase / 2.0 + 0.6)
    rpm = 180.0 + 65.0 * (1.0 + math.sin(phase / 1.4)) / 2.0
    if step % 42 >= 34:
        ax += 0.18
        ay -= 0.14
        current += 0.08
        rpm += 18.0
        status = "DEMO_ALERT"
    else:
        status = "DEMO_OK"

    return normalize_sample(
        {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "ax": ax,
            "ay": ay,
            "az": az,
            "current": current,
            "rpm": rpm,
            "rpm_norm": rpm / RPM_NORM_BASE,
            "status": status,
        },
        "Public Demo Replay",
    )


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #1f2937;
            --muted: #667085;
            --line: #d9e2ef;
            --panel: #ffffff;
            --page: #f3f6fb;
            --green: #16a34a;
            --red: #dc2626;
            --amber: #d97706;
        }
        header[data-testid="stHeader"] { background: rgba(243, 246, 251, 0.72); }
        .block-container { max-width: 1180px; padding-top: 0.9rem; padding-bottom: 2rem; }
        div[data-testid="stAppViewContainer"] { background: var(--page); }
        .top-shell {
            display: flex; align-items: center; justify-content: space-between; min-height: 22px;
            color: #98a2b3; font-size: 0.72rem; font-weight: 700; margin-bottom: 0.45rem;
        }
        .run-dot {
            width: 8px; height: 8px; display: inline-block; margin-right: 0.35rem;
            border-radius: 50%; background: var(--green); box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.13);
        }
        .demo-dot { background: var(--amber); box-shadow: 0 0 0 4px rgba(217, 119, 6, 0.13); }
        .stop-dot { background: var(--red); box-shadow: 0 0 0 4px rgba(220, 38, 38, 0.13); }
        .control-strip { margin: 0.1rem 0 0.7rem; }
        .flow-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.72rem; margin-bottom: 0.75rem; }
        .flow-card, .cloud-card {
            border: 1px solid var(--line); border-radius: 7px; background: var(--panel);
            box-shadow: 0 10px 24px rgba(31, 41, 55, 0.04);
        }
        .flow-card { min-height: 78px; padding: 0.82rem 0.95rem; }
        .flow-title { color: #344054; font-size: 0.78rem; font-weight: 800; margin-bottom: 0.36rem; }
        .flow-text { color: #475467; font-size: 0.76rem; line-height: 1.62; }
        .body-grid { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 0.9rem; align-items: start; }
        .metric-grid {
            display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));
            column-gap: 1.45rem; row-gap: 0.85rem; margin: 0 0 1.15rem;
        }
        .metric-name { color: var(--muted); font-size: 0.72rem; font-weight: 700; margin-bottom: 0.18rem; }
        .metric-value { color: #202938; font-size: 1.58rem; font-weight: 500; line-height: 1.15; overflow-wrap: anywhere; }
        .metric-value.status { font-size: 1.35rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .cloud-card { padding: 1.05rem 1.15rem; min-height: 112px; }
        .cloud-title { color: #101828; font-size: 0.9rem; font-weight: 800; margin-bottom: 0.55rem; }
        .cloud-line { color: #344054; font-size: 0.78rem; line-height: 1.76; font-weight: 600; }
        .cloud-line span { color: #475467; font-weight: 500; }
        .table-title { margin: 0.75rem 0 0.45rem; color: var(--ink); font-size: 1rem; font-weight: 800; }
        @media (max-width: 1040px) {
            .body-grid { grid-template-columns: 1fr; }
            .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
            .flow-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media (max-width: 640px) {
            .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .flow-grid { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_pipeline_cards(data_source: str) -> None:
    cards = [
        ("1. Device", zh(r"\u7ec8\u7aef\u4e0a\u62a5 ax / ay / az / current / rpm / status")),
        ("2. Huawei Cloud", zh(r"\u4ece IoTDA device shadow \u62c9\u53d6 reported properties")),
        ("3. Public Demo", data_source),
        ("4. Dashboard", zh(r"\u5916\u7f51\u9875\u9762\u5b9e\u65f6\u5237\u65b0\u8fd0\u884c\u72b6\u6001")),
    ]
    html = ['<div class="flow-grid">']
    for title, text in cards:
        html.append(f'<div class="flow-card"><div class="flow-title">{title}</div><div class="flow-text">{text}</div></div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_metric_cards(sample: dict | None) -> None:
    if sample is None:
        sample = {"ax": 0, "ay": 0, "az": 0, "current": 0, "rpm_norm": 0, "status": "WAITING"}
    cards = [
        ("ax", f"{sample['ax']:.4f}", ""),
        ("ay", f"{sample['ay']:.4f}", ""),
        ("az", f"{sample['az']:.4f}", ""),
        ("current", f"{sample['current']:.4f}", ""),
        ("rpm_norm", f"{sample['rpm_norm']:.6f}", ""),
        ("status", str(sample["status"]), " status"),
    ]
    html = ['<div class="metric-grid">']
    for name, value, value_class in cards:
        html.append(f'<div class="metric-item"><div class="metric-name">{name}</div><div class="metric-value{value_class}">{value}</div></div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_cloud_card(sample: dict | None, settings: dict, mode_label: str, data_source: str) -> None:
    source = sample["source"] if sample else "-"
    ts = sample["timestamp"] if sample else "-"
    endpoint = settings["endpoint"] or "Not configured"
    st.markdown(
        f"""
        <div class="cloud-card">
          <div class="cloud-title">{zh(r"\u5916\u7f51\u6f14\u793a\u6570\u636e\u6e90")}</div>
          <div class="cloud-line">{zh(r"\u6a21\u5f0f")}<span>: {mode_label}</span></div>
          <div class="cloud-line">{zh(r"\u670d\u52a1")}<span>: {settings["service_id"] or "Motor"}</span></div>
          <div class="cloud-line">{zh(r"\u7aef\u70b9")}<span>: {endpoint}</span></div>
          <div class="cloud-line">{zh(r"\u6765\u6e90")}<span>: {source}</span></div>
          <div class="cloud-line">{zh(r"\u94fe\u8def")}<span>: {data_source}</span></div>
          <div class="cloud-line">{zh(r"\u6700\u65b0\u65f6\u95f4")}<span>: {ts}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_figure() -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=440,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": zh(r"\u7b49\u5f85\u6f14\u793a\u6570\u636e"),
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {"size": 18, "color": "#667085"},
            }
        ],
    )
    return fig


def build_figure(history_df: pd.DataFrame) -> go.Figure:
    if history_df.empty:
        return empty_figure()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.64, 0.36],
        specs=[[{}], [{"secondary_y": True}]],
        subplot_titles=(zh(r"\u4e09\u8f74\u632f\u52a8\u6570\u636e"), zh(r"\u7535\u6d41\u4e0e\u8f6c\u901f\u5f52\u4e00\u5316\u503c")),
    )
    traces = [
        ("ax", "#2563eb", 1, 1, False),
        ("ay", "#16a34a", 1, 1, False),
        ("az", "#dc2626", 1, 1, False),
        ("current", "#7c3aed", 2, 1, False),
        ("rpm_norm", "#f97316", 2, 1, True),
    ]
    for name, color, row, col, secondary_y in traces:
        fig.add_trace(
            go.Scatter(x=history_df["window"], y=history_df[name], name=name, mode="lines", line=dict(color=color, width=2)),
            row=row,
            col=col,
            secondary_y=secondary_y,
        )

    fig.update_layout(
        template="plotly_white",
        height=440,
        margin=dict(l=28, r=24, t=54, b=20),
        legend=dict(orientation="h", y=1.05, x=0.03, font=dict(size=10)),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#475467", size=11),
    )
    fig.update_traces(line_shape="hv")
    fig.update_xaxes(showgrid=False, zeroline=False, title_text="", row=1, col=1)
    fig.update_xaxes(showgrid=False, zeroline=False, title_text="", row=2, col=1)
    fig.update_yaxes(gridcolor="#e6edf5", zeroline=False, range=[-1.55, 1.5], row=1, col=1, title_text="ax / ay / az")
    fig.update_yaxes(gridcolor="#e6edf5", zeroline=False, range=[0, 1.0], row=2, col=1, secondary_y=False, title_text="current")
    fig.update_yaxes(gridcolor="#e6edf5", zeroline=False, range=[0, 1.5], row=2, col=1, secondary_y=True, title_text="rpm_norm")
    return fig


def get_sample(stream_mode: str, settings: dict) -> tuple[dict, str, str]:
    if stream_mode == "Demo replay":
        sample = build_demo_sample(st.session_state.demo_tick)
        st.session_state.demo_tick += 1
        st.session_state.last_error = zh(r"\u5f53\u524d\u4e3a Demo replay \u6a21\u5f0f\uff0c\u9002\u5408\u5916\u7f51\u5c55\u793a\u754c\u9762\u3002")
        return sample, "DEMO REPLAY", "Demo replay stream"

    live_sample, error_text = read_huawei_shadow_sample(settings)
    if live_sample is not None:
        st.session_state.last_error = ""
        return live_sample, "LIVE CLOUD", "Huawei Cloud IoTDA shadow"

    sample = build_demo_sample(st.session_state.demo_tick)
    st.session_state.demo_tick += 1
    st.session_state.last_error = error_text
    return sample, "DEMO FALLBACK", "Demo replay fallback"


def main() -> None:
    st.set_page_config(
        page_title=zh(r"\u7535\u673a\u8fd0\u884c\u72b6\u6001\u5916\u7f51\u6f14\u793a"),
        page_icon="M",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    init_state()
    inject_styles()

    settings = load_huawei_settings()

    st.markdown(
        f"""
        <div class="top-shell">
          <span>&gt;</span>
          <span>{zh(r"\u4fdd\u7559 app.py \u4f5c\u4e3a\u672c\u5730\u7248\uff0c\u5f53\u524d\u9875\u9762\u4e3a\u53ef\u90e8\u7f72\u7684\u5916\u7f51\u6f14\u793a\u7248")}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="control-strip">', unsafe_allow_html=True)
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([1.3, 1.0, 1.1, 1.6], gap="medium")
    with ctrl1:
        stream_mode = st.selectbox("Data mode", ["Auto: Cloud first", "Demo replay"], index=0)
    with ctrl2:
        running = st.toggle("Auto refresh", value=True)
    with ctrl3:
        refresh_seconds = st.slider("Refresh interval", 0.2, 2.0, DEFAULT_REFRESH_SECONDS, 0.1)
    with ctrl4:
        if st.button(zh(r"\u6e05\u7a7a\u66f2\u7ebf")):
            st.session_state.history = []
    st.markdown("</div>", unsafe_allow_html=True)

    sample, mode_label, data_source = get_sample(stream_mode, settings)
    reset_history_if_source_changed(f"{stream_mode}|{mode_label}")
    append_sample(sample)

    latest = st.session_state.history[-1] if st.session_state.history else None
    history_df = pd.DataFrame(st.session_state.history)
    if not history_df.empty:
        history_df["window"] = range(-len(history_df) + 1, 1)

    dot_class = "run-dot"
    if mode_label.startswith("DEMO"):
        dot_class = "run-dot demo-dot"
    state_text = f"{mode_label}..."
    st.markdown(f'<div class="top-shell"><span>{zh(r"\u8fd0\u884c\u72b6\u6001")}</span><span><span class="{dot_class}"></span>{state_text}</span></div>', unsafe_allow_html=True)

    render_pipeline_cards(data_source)
    st.markdown('<div class="body-grid"><div>', unsafe_allow_html=True)
    render_metric_cards(latest)
    st.markdown("</div><div>", unsafe_allow_html=True)
    render_cloud_card(latest, settings, mode_label, data_source)
    st.markdown("</div></div>", unsafe_allow_html=True)

    if st.session_state.last_error:
        if mode_label == "LIVE CLOUD":
            st.warning(st.session_state.last_error)
        else:
            st.info(st.session_state.last_error)

    st.plotly_chart(build_figure(history_df), use_container_width=True, config={"displayModeBar": False})

    st.markdown(f'<div class="table-title">{zh(r"\u5b9e\u65f6\u6570\u636e")}</div>', unsafe_allow_html=True)
    if history_df.empty:
        st.info(zh(r"\u6682\u65e0\u6570\u636e\u3002\u8bf7\u5148\u914d\u7f6e\u534e\u4e3a\u4e91 IoTDA secrets\uff0c\u6216\u5207\u6362\u5230 Demo replay \u6a21\u5f0f\u3002"))
    else:
        recent = history_df.tail(10).copy()
        for col, digits in [("ax", 4), ("ay", 4), ("az", 4), ("current", 4), ("rpm", 0), ("rpm_norm", 6)]:
            recent[col] = recent[col].map(lambda x, d=digits: f"{x:.{d}f}")
        st.dataframe(
            recent[["timestamp", "source", "ax", "ay", "az", "current", "rpm", "rpm_norm", "status"]],
            use_container_width=True,
            hide_index=True,
            height=248,
        )

    if running:
        time.sleep(refresh_seconds)
        rerun_page()


if __name__ == "__main__":
    main()
