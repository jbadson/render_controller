import React from 'react';
import './JobSummary.css';
import ProgressBar from './ProgressBar';
import { fmtTime, getBasename } from './util';


/**
 * Widget that displays summary render job info.
 * @prop {string} filePath - Path to project file
 * @prop {string} status - Job status
 * @prop {float} progress - Percent complete
 * @prop {float} timeRemaining - Time until render complete (sec)
 * @prop {float} timeElapsed - Rendering time (sec)
 */
function JobSummary(props) {
    let style = "summary-container";
    if (props.isSelected) {
      style += "-selected";
    }

    let fillClass = "progress-fill";
    if (props.status === "Rendering") {
      fillClass += "-rendering";
    } else if (props.status === "Stopped") {
      fillClass += "-stopped";
    } else if (props.status === "Finished") {
      fillClass += "-finished"
    } else if (props.status === "Waiting") {
      fillClass += "-waiting"
    }

    return (
      <div className={style} onClick={props.onClick} >
        <ul>
          <li className="layout-row">
            <p className="left">{getBasename(props.filePath)}</p>
            <p className="right">{props.status}</p>
          </li>
          <li className="layout-row">
            <ProgressBar
              barClass="summary-progress-bar"
              fillClass={fillClass}
              percent={props.progress}
              noText={true}
            />
          </li>
          <li className="layout-row">
            <p className="left">Time elapsed: {fmtTime(props.timeElapsed)}</p>
            <p className="right">Time remaining: {fmtTime(props.timeRemaining)}</p>
          </li>
        </ul>
      </div>
    )
}


export default JobSummary;
