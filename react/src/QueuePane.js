import React, { Component } from 'react';
import './QueuePane.css'
import JobSummary from './JobSummary';


/**
 * Widget that displays a panel of job status widgets
 * @param {Array<Object>} serverJobs - Array of job status data
 * @param {string} selectedJob - ID of selected job.
 * @param {function} onJobClick - Function to call when a job widget is clicked.
 */
class QueuePane extends Component {

  renderQueueBox(job) {
    return (
      <li className="layout-row" key={job.id}>
        <JobSummary
          filePath={job.path}
          status={job.status}
          timeRemaining={job.time_remaining}
          timeElapsed={job.time_elapsed}
          progress={job.progress}
          isSelected={(job.id === this.props.selectedJob) ? true : false}
          onClick={() => this.props.onJobClick(job.id)}
        />
    </li>
    )
  }

  render() {
    if (!this.props.serverJobs) {
      return <div>Error: No data to render</div>
    }
    return (
      <div className="qp-container">
        <ul>
          <li className="qp-row">
            <div className="qp-header">Render Queue</div>
          </li>
          <li className="qp-row">
            <div className="qp-inner">
              <ul>
                {this.props.serverJobs.map(job => this.renderQueueBox(job))}
              </ul>
            </div>
          </li>
        </ul>
      </div>
    )
  }
}


export default QueuePane;
