const Icon = ({ name, size = 14, stroke = 1.5, style = {} }) => {
  const c = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: stroke, strokeLinecap: "round", strokeLinejoin: "round", style };
  const p = {
    chat: <path d="M4 5h16v11H9l-5 4V5z"/>,
    plus: <path d="M12 5v14M5 12h14"/>,
    home: <><path d="M3 11l9-8 9 8"/><path d="M5 10v10a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V10"/></>,
    history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/></>,
    search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/></>,
    eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></>,
    mic: <><rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 18v4"/></>,
    zap: <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z"/>,
    cube: <><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16zM3.27 6.96 12 12.01l8.73-5.05M12 22.08V12"/></>,
    download: <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>,
    folder: <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>,
    x: <path d="M18 6 6 18M6 6l12 12"/>,
    chevron: <path d="m6 9 6 6 6-6"/>,
    arrow_right: <path d="M5 12h14M13 5l7 7-7 7"/>,
    arrow_left: <path d="M19 12H5m6-7-7 7 7 7"/>,
    paperclip: <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 17.98 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>,
    sparkle: <><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></>,
    cpu: <><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></>,
    gpu: <><rect x="2" y="7" width="20" height="12" rx="2"/><circle cx="8" cy="13" r="2.5"/><circle cx="16" cy="13" r="2.5"/></>,
    ram: <><rect x="2" y="8" width="20" height="10" rx="1"/><path d="M6 12v2M10 12v2M14 12v2M18 12v2"/></>,
    check_c: <><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></>,
    alert: <><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01"/></>,
    min: <path d="M5 12h14"/>,
    max: <rect x="5" y="5" width="14" height="14"/>,
    restore: <><rect x="7" y="7" width="12" height="12"/><path d="M5 17V5h12"/></>,
    close: <path d="M6 6l12 12M18 6 6 18"/>,
    check: <path d="M20 6 9 17l-5-5"/>,
    waveform: <path d="M2 12h2M7 8v8M12 4v16M17 8v8M22 12h-2"/>,
    target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></>,
    eye_off: <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-10-8-10-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24M1 1l22 22"/>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></>,
    moon: <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>,
    lock: <><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></>,
    shield: <path d="M12 2 4 5v7c0 4.5 3.5 8 8 10 4.5-2 8-5.5 8-10V5l-8-3z"/>,
    layers: <><path d="m12 2 9 5-9 5-9-5 9-5z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 13h6M9 17h6"/></>,
    pin: <><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></>,
    pencil: <><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></>,
    trash: <><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M10 11v6M14 11v6"/></>,
    dots: <><circle cx="12" cy="5"  r="2.1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="2.1" fill="currentColor" stroke="none"/><circle cx="12" cy="19" r="2.1" fill="currentColor" stroke="none"/></>,
    embed: <><circle cx="5" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.6" fill="currentColor" stroke="none"/><path d="M3 5h18M3 19h18"/></>,
  };
  return <svg {...c}>{p[name]}</svg>;
};
window.Icon = Icon;

const Logo = ({ size = 32, style = {} }) => (
  <svg width={size} height={size} viewBox="0 0 128 128" style={style}>
    <defs>
      <linearGradient id={`logo-bg-${size}`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#1F2937"/>
        <stop offset="100%" stopColor="#0F172A"/>
      </linearGradient>
    </defs>
    <rect x="4" y="4" width="120" height="120" rx="26" fill={`url(#logo-bg-${size})`}/>
    <g stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.85">
      <line x1="32" y1="40" x2="60" y2="28"/>
      <line x1="60" y1="28" x2="88" y2="52"/>
      <line x1="88" y1="52" x2="54" y2="68"/>
      <line x1="54" y1="68" x2="40" y2="96"/>
      <line x1="88" y1="52" x2="96" y2="88"/>
    </g>
    <g fill="#60a5fa">
      <circle cx="32" cy="40" r="5"/>
      <circle cx="60" cy="28" r="4"/>
      <circle cx="88" cy="52" r="7"/>
      <circle cx="54" cy="68" r="5"/>
      <circle cx="96" cy="88" r="4"/>
      <circle cx="40" cy="96" r="5"/>
    </g>
  </svg>
);
window.Logo = Logo;
