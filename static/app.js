// Convert any <time data-utc="..."> elements to the user's local timezone.
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

// Palette used for stacked-by-sport charts.
const STACK_COLORS = [
    '#5fbf9f', '#e8a85c', '#7aa6ff', '#d77ad3',
    '#e8d35c', '#7adcd5', '#e87a8a', '#9d8cf2',
    '#777777',
];

// Mirror of analytics/sports.py overrides so chart legends read nicely.
const FRIENDLY_SPORT_MAP = {
    'weightlifting_msk': 'Strength Trainer',
    'weightlifting': 'Weightlifting',
    'stairmaster': 'StairMaster',
    'hiit': 'HIIT',
    'f45_training': 'F45 Training',
    'jiu_jitsu': 'Jiu-Jitsu',
    'ice_bath': 'Ice Bath',
    'hot_yoga': 'Hot Yoga',
    'cross_country_skiing': 'Cross-Country Skiing',
    'mountain_biking': 'Mountain Biking',
    'rock_climbing': 'Rock Climbing',
    'horseback_riding': 'Horseback Riding',
    'hiking_rucking': 'Hiking / Rucking',
    'martial_arts': 'Martial Arts',
    'functional_fitness': 'Functional Fitness',
    'table_tennis': 'Table Tennis',
    'ice_hockey': 'Ice Hockey',
    'field_hockey': 'Field Hockey',
    'water_polo': 'Water Polo',
    'jumping_rope': 'Jumping Rope',
    'manual_labor': 'Manual Labour',
    'public_speaking': 'Public Speaking',
};
function FRIENDLY_SPORT(name) {
    if (!name) return '(unknown)';
    const k = name.toLowerCase();
    if (FRIENDLY_SPORT_MAP[k]) return FRIENDLY_SPORT_MAP[k];
    return k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function renderHorizontalBar(canvasId, labels, values, unit) {
    const el = document.getElementById(canvasId);
    if (!el || !values || !values.length) return;
    new Chart(el, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: STACK_COLORS[0],
                borderWidth: 0,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: (ctx) => `${ctx.parsed.x.toLocaleString()} ${unit || ''}` } },
            },
            scales: {
                x: { beginAtZero: true, ticks: { precision: 0 } },
                y: { ticks: { autoSkip: false } },
            },
        },
    });
    el.parentElement.style.height = `${Math.max(180, labels.length * 28)}px`;
    el.style.height = `${Math.max(180, labels.length * 28)}px`;
}

function renderStackedBar(canvasId, payload, labelTransform) {
    const el = document.getElementById(canvasId);
    if (!el || !payload || !payload.datasets || !payload.datasets.length) return;
    const datasets = payload.datasets.map((ds, i) => ({
        label: labelTransform ? labelTransform(ds.label) : ds.label,
        data: ds.data,
        backgroundColor: STACK_COLORS[i % STACK_COLORS.length],
        borderWidth: 0,
    }));
    new Chart(el, {
        type: 'bar',
        data: { labels: payload.labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } },
            scales: {
                x: { stacked: true, ticks: { maxTicksLimit: 12, autoSkip: true } },
                y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
            },
        },
    });
    el.parentElement.style.height = '320px';
    el.style.height = '320px';
}

function renderLine(canvasId, points) {
    const el = document.getElementById(canvasId);
    if (!el || !points || !points.length) return;
    new Chart(el, {
        type: 'line',
        data: {
            labels: points.map(p => p.day || p.date),
            datasets: [{
                data: points.map(p => p.value),
                borderColor: '#7aa6ff',
                backgroundColor: 'rgba(122,166,255,0.12)',
                tension: 0.25,
                fill: true,
                pointRadius: points.length > 60 ? 0 : 2,
                borderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { maxTicksLimit: 8, autoSkip: true } },
                y: { beginAtZero: false },
            },
        },
    });
    el.parentElement.style.height = '260px';
    el.style.height = '260px';
}
