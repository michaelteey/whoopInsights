/* whoopInsights — chart and UI helpers, ApexCharts edition */

const CHART_COLORS = {
    mint:   '#3ee6ad',
    blue:   '#6f9eff',
    yellow: '#f5d76a',
    pink:   '#ee7aa1',
    purple: '#9d8cf2',
    cyan:   '#7adcd5',
    orange: '#e8a85c',
    grey:   '#6b7177',
};

const STACK_PALETTE = [
    CHART_COLORS.mint,
    CHART_COLORS.blue,
    CHART_COLORS.yellow,
    CHART_COLORS.pink,
    CHART_COLORS.purple,
    CHART_COLORS.cyan,
    CHART_COLORS.orange,
    CHART_COLORS.grey,
];

const FRIENDLY_SPORT_MAP = {
    'weightlifting_msk': 'strength trainer',
    'weightlifting': 'weightlifting',
    'stairmaster': 'stairmaster',
    'hiit': 'hiit',
    'f45_training': 'f45 training',
    'jiu_jitsu': 'jiu-jitsu',
    'ice_bath': 'ice bath',
    'hot_yoga': 'hot yoga',
    'cross_country_skiing': 'cross-country skiing',
    'mountain_biking': 'mountain biking',
    'rock_climbing': 'rock climbing',
    'horseback_riding': 'horseback riding',
    'hiking_rucking': 'hiking / rucking',
    'martial_arts': 'martial arts',
    'functional_fitness': 'functional fitness',
    'table_tennis': 'table tennis',
    'ice_hockey': 'ice hockey',
    'field_hockey': 'field hockey',
    'water_polo': 'water polo',
    'jumping_rope': 'jumping rope',
    'public_speaking': 'public speaking',
};
function FRIENDLY_SPORT(name) {
    if (!name) return '(unknown)';
    const k = name.toLowerCase();
    if (FRIENDLY_SPORT_MAP[k]) return FRIENDLY_SPORT_MAP[k];
    return k.replace(/_/g, ' ');
}

/* shared ApexCharts config to keep chart styling consistent */
function baseChartOptions() {
    return {
        chart: {
            background: 'transparent',
            toolbar: { show: false },
            animations: { enabled: true, speed: 350 },
            fontFamily: "'JetBrains Mono', monospace",
        },
        theme: { mode: 'dark' },
        grid: {
            borderColor: '#1a1d22',
            strokeDashArray: 0,
            xaxis: { lines: { show: false } },
            yaxis: { lines: { show: true } },
            padding: { left: 8, right: 8, top: 0, bottom: 0 },
        },
        dataLabels: { enabled: false },
        tooltip: {
            theme: 'dark',
            style: { fontFamily: "'JetBrains Mono', monospace", fontSize: '12px' },
        },
        legend: {
            position: 'bottom',
            labels: { colors: '#6b7177' },
            markers: { width: 8, height: 8, radius: 2 },
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
        },
    };
}

const AXIS_LABEL_STYLE = {
    colors: '#6b7177',
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '10px',
};

function renderLine(elId, points, opts = {}) {
    const el = document.getElementById(elId);
    if (!el || !points || !points.length) return;
    const colour = opts.color || CHART_COLORS.mint;
    const options = {
        ...baseChartOptions(),
        chart: { ...baseChartOptions().chart, type: 'area', height: 280 },
        series: [{ name: opts.label || 'value', data: points.map(p => p.value) }],
        xaxis: {
            categories: points.map(p => p.day || p.date),
            labels: { style: AXIS_LABEL_STYLE, rotate: 0, hideOverlappingLabels: true },
            axisBorder: { show: false },
            axisTicks: { show: false },
        },
        yaxis: {
            labels: { style: AXIS_LABEL_STYLE, formatter: (v) => v == null ? '' : Math.round(v * 100) / 100 },
        },
        colors: [colour],
        stroke: { curve: 'smooth', width: 2 },
        fill: {
            type: 'gradient',
            gradient: { shadeIntensity: 0.5, opacityFrom: 0.25, opacityTo: 0, stops: [0, 100] },
        },
        markers: { size: points.length > 60 ? 0 : 3, strokeWidth: 0, colors: [colour] },
        legend: { show: false },
    };
    new ApexCharts(el, options).render();
}

function renderStackedBar(elId, payload, labelTransform) {
    const el = document.getElementById(elId);
    if (!el || !payload || !payload.datasets || !payload.datasets.length) return;
    const series = payload.datasets.map(ds => ({
        name: labelTransform ? labelTransform(ds.label) : ds.label,
        data: ds.data,
    }));
    const colours = payload.datasets.map((_, i) => STACK_PALETTE[i % STACK_PALETTE.length]);
    const options = {
        ...baseChartOptions(),
        chart: { ...baseChartOptions().chart, type: 'bar', stacked: true, height: 340 },
        series,
        xaxis: {
            categories: payload.labels,
            labels: { style: AXIS_LABEL_STYLE, hideOverlappingLabels: true },
            axisBorder: { show: false },
            axisTicks: { show: false },
        },
        yaxis: { labels: { style: AXIS_LABEL_STYLE } },
        colors: colours,
        plotOptions: { bar: { columnWidth: '60%', borderRadius: 0 } },
        stroke: { show: false, width: 0 },
    };
    new ApexCharts(el, options).render();
}

function renderHorizontalBar(elId, labels, values, unit) {
    const el = document.getElementById(elId);
    if (!el || !values || !values.length) return;
    const options = {
        ...baseChartOptions(),
        chart: {
            ...baseChartOptions().chart,
            type: 'bar',
            height: Math.max(220, labels.length * 32 + 60),
        },
        series: [{ name: unit || 'value', data: values }],
        xaxis: {
            categories: labels,
            labels: { style: AXIS_LABEL_STYLE, formatter: (v) => Number(v).toLocaleString() },
            axisBorder: { show: false },
            axisTicks: { show: false },
        },
        yaxis: { labels: { style: AXIS_LABEL_STYLE } },
        colors: [CHART_COLORS.mint],
        plotOptions: { bar: { horizontal: true, barHeight: '60%', borderRadius: 0 } },
        legend: { show: false },
        stroke: { show: false, width: 0 },
        tooltip: {
            ...baseChartOptions().tooltip,
            y: { formatter: (v) => `${Number(v).toLocaleString()} ${unit || ''}` },
        },
    };
    new ApexCharts(el, options).render();
}

/* convert <time data-utc="..."> elements to the viewer's timezone */
document.querySelectorAll('time[data-utc]').forEach(el => {
    const utc = el.dataset.utc;
    if (!utc || utc === 'unknown' || utc === 'local') return;
    const d = new Date(utc.endsWith('Z') ? utc : utc + 'Z');
    if (isNaN(d.getTime())) return;
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const tzShort = new Intl.DateTimeFormat('en', { timeZoneName: 'short' })
        .formatToParts(d).find(p => p.type === 'timeZoneName')?.value || tz;
    const formatted = d.toLocaleString('en-GB', {
        year: 'numeric', month: 'short', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false,
    });
    el.textContent = `${formatted} ${tzShort}`;
    el.title = `${utc} (UTC)`;
});
