// Formats time like {days}d {hrs}h {min}m {sec}s
function fmtTime(time) {
  let m, s, h, d;
  m = Math.floor(time / 60);
  s = time % 60;
  h = Math.floor(m / 60);
  m = m % 60; // Get remaining min from total
  d = Math.floor(h / 24);
  h = h % 24; // Get remaining hr from total
  let timestr = s.toFixed(1) + "s";
  if (time >= 60) {
    timestr = m.toFixed(0) + "m " + s.toFixed(0) + "s";
  }
  if (time >= 3600) {
    timestr = h.toFixed(0) + "h " + timestr;
  }
  if (time >= 86400) {
    timestr = d.toFixed(0) + "d " + timestr;
  }
  return timestr;
}

function getBasename(path) {
  const parts = path.split('/')
  return parts[parts.length - 1]
}

export { fmtTime, getBasename };
