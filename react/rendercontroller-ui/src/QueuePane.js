import React, { Component } from 'react';
import './QueuePane.css'
import axios from 'axios';
import JobSummary from './JobSummary';


/**
 * Widget that displays a panel of job status widgets
 * @param {string} url - URL of REST API
 * @param {int} pollInterval - Server poll interval (milliseconds)
 * @param {function} onJobClick - Function to call when a job widget is clicked.
 */
class QueuePane extends Component {
  constructor(props) {
    super(props);
    this.state = {
      data: null
    }
  }

  getUpdate() {
    // Fetch data from server and update UI
    axios.get(this.props.url + "/job/summary")
      .then(
        (result) => {
          this.setState({data: result.data})
        },
        (error) => {
          this.setState({error: error})
        }
      )
  }

  componentDidMount() {
    this.getUpdate()
    this.interval = setInterval(() => this.getUpdate(), this.props.pollInterval);
  }

  componentWillUnmount() {
    clearInterval(this.interval);
  }

  renderQueueBox(job) {
    return (
      <li className="layout-row" key={job.id}>
        <JobSummary
          filePath={job.file_path}
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
    const { data, error } = this.state;
    if (error) {
      return <div>Error {error.message}</div>
    } else if (!data) {
      //FIXME will be empty if nothing in queue
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
                {data.map(job => this.renderQueueBox(job))}
              </ul>
            </div>
          </li>
        </ul>
      </div>
    )
  }
}


export default QueuePane;
