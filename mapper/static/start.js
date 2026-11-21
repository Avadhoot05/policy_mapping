// Start page: "Start analysis" runs the analysis for one company and shows the link to the new report.
document.querySelectorAll('section[data-slug]').forEach(section => {
  section.querySelector('.run').onclick = ev => {
    const button = ev.target;
    const status = section.querySelector('.status');
    button.disabled = true;
    status.textContent = 'Running analysis…';
    fetch(`/api/c/${section.dataset.slug}/runs`, {method: 'POST'})
      .then(r => r.json().then(j => { if (!r.ok) throw new Error(j.error); return j; }))
      .then(j => {
        status.innerHTML = `Done in ${j.seconds} s · <a href="${j.report_url}"><b>Open report</b></a>`;
        button.disabled = false;
      })
      .catch(err => {
        status.textContent = 'Failed: ' + err.message;
        button.disabled = false;
      });
  };
});
