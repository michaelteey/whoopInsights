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
