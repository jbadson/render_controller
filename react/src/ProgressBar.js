import React from 'react';
import './ProgressBar.css';

/**
 * Horizontal progress bar widget
 * @prop {string} barClass - className of progress bar inner div. Can be used
 *    to set height, border-radius, etc.
 * @prop {string} fillClass - className of progress bar fill.
 * @prop {float} percent - Progress percent
 * @prop {boolean} noText - Do not show percent in text overlay.
 */
function ProgressBar(props) {
  const barClass = props.barClass || "progress-bar";
  return (
    <div className="progress-container">
      <div className={barClass}>
        <ProgressFill fillClass={props.fillClass} percent={props.percent} />
      </div>
        {props.noText ||
          <span className="progress-number">{props.percent.toFixed(1)} %</span>
        }
    </div>
  )
}


function ProgressFill(props) {
  const fillClass = props.fillClass || "progress-fill"
  return <div className={fillClass} style={{ width: `${props.percent}%`}} />
}


export default ProgressBar;
