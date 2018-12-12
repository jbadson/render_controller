import React, { Component } from 'react';
import './JobStatus.css';
import axios from 'axios';
import ProgressBar from './ProgressBar';
import CheckBox from './CheckBox';
import { fmtTime, getBasename } from './util';

/**
 * Render node status widget.
 * @param {string} url - REST API URL
 * @param {string} name - Node Name
 * @param {string} jobId - ID of job this node is rendering
 * @param {boolean} isEnabled - Is node enabled for rendering?
 * @param {int} frame - Fram node is currently rendering
 * @param {float} progress - Percent frame complete
 */
class NodeStatusBox extends Component {
  handleToggle() {
    let action = "enable";
    if (this.props.isEnabled) {
      action = "disable";
    }
    axios.get(this.props.url + "/node/" + action + "/" + this.props.name + "/" + this.props.jobId)
  }

  render() {
    return (
      <div className="node-status-box" key={this.props.name}>
        <ul>
          <li className="layout-row">
            <div className="left">{this.props.name}</div>
            <CheckBox
                className="right"
                label="Enabled:&nbsp;"
                value={this.props.name}
                checked={this.props.isEnabled}
                onChange={() => this.handleToggle()}
            />
          </li>
          <li className="layout-row">
            <ProgressBar barClass="node-progress-bar" percent={this.props.progress} noText={true} />
          </li>
          <li className="jsp-row">
            <p className="left">Frame: {this.props.frame}</p>
            <p className="right">{this.props.progress.toFixed(0)} % Complete</p>
          </li>
        </ul>
      </div>
    )
  }
}


/**
 * Widget that displays detailed render job info.
 * @param {string} filePath - Path to project file
 * @param {string} status - Job status
 * @param {float} progress - Percent complete
 * @param {float} timeRemaining - Time until render complete (sec)
 * @param {float} timeElapsed - Rendering time (sec)
 */
function JobStatusBox(props) {
    let fillClass = "progress-fill";
    if (props.status === "Rendering") {
      fillClass += "-rendering";
    } else if (props.status === "Stopped") {
      fillClass += "-stopped";
    } else if (props.status === "Finished") {
      fillClass += "-finished"
    }

    return (
      <div className="jsb-container" onClick={props.onClick} >
        <ul>
          <li className="layout-row">
            <p className="left">Status: {props.status}</p>
            <p className="right">Start frame: {props.startFrame}</p>
          </li>
          <li className="layout-row">
            <p className="left">Path: {props.filePath}</p>
            <p className="right">End frame: {props.endFrame}</p>
          </li>
          <li className="layout-row">
            <div className="left-3pane">Time elapsed: {fmtTime(props.timeElapsed)}</div>
            <div className="center-3pane">Avg time/frame: {fmtTime(props.timeAvg)}</div>
            <div className="right-3pane">Time remaining: {fmtTime(props.timeRemaining)}</div>
          </li>
          <li className="layout-row">
            <ProgressBar fillClass={fillClass} percent={props.progress} />
          </li>
        </ul>
      </div>
    )
}


/**
 * Widget to display comprehensive job info with render nodes.
 * @param {string} jobId - ID of render job
 * @param {string} url - REST API URL
 * @param {int} pollInterval - How often to poll API for updates (milliseconds)
 */
class JobStatusPane extends Component {
  constructor(props) {
    super(props)
    this.state = {
      data: null,
      error: null,
    }
    this.startJob = this.startJob.bind(this);
    this.stopJob = this.stopJob.bind(this);
    this.enqueueJob = this.enqueueJob.bind(this);
    this.deleteJob = this.deleteJob.bind(this);
  }

  startJob() {
    axios.post(this.props.url + "/job/start/" + this.props.jobId)
      .then(
        (result) => {console.log(result)},
        (error) => {console.error(error.message)}
      );
  }

  stopJob() {
    axios.post(this.props.url + "/job/stop/" + this.props.jobId)
    .then(
      //FIXME: Add confirmation of some kind
      (result) => {console.log(result)},
      (error) => {console.error(error.message)}
    );
  }

  enqueueJob() {
    axios.post(this.props.url + "/job/enqueue/" + this.props.jobId)
    .then(
      //FIXME: Add note about starting job manually
      (result) => {console.log(result)},
      (error) => {console.error(error.message)}
    );
  }

  deleteJob() {
    axios.post(this.props.url + "/job/delete/" + this.props.jobId)
    .then(
      //FIXME: Add confirmation and warning if job is not stopped
      (result) => {console.log(result)},
      (error) => {console.error(error.message)}
    );
  }

  getUpdate() {
    axios.get(this.props.url + "/job/status/" + this.props.jobId)
      .then(result => {
        this.setState({data: result.data});
        },
        error => {this.setState({error: error});
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

  renderNodeBox(name, nodeStatus) {
    return (
      <NodeStatusBox
        key={name}
        name={name}
        jobId={this.props.jobId}
        url={this.props.url}
        isRendering={nodeStatus.rendering}
        isEnabled={nodeStatus.enabled}
        frame={nodeStatus.frame}
        progress={nodeStatus.progress}
      />
    )
  }

  render() {
    const { data, error } = this.state;
    if (error) {
      return <p>Error: {error.message}</p>
    } else if (!data) {
      return <p>No data to display</p>
    }
    return (
      <div className="jsp-container">
        <ul>
          <li className="jsp-row">
            <div className="jsp-header">{getBasename(data.file_path)}</div>
          </li>
          <li className="jsp-row">
            <div className="jsp-inner">
              <ul>
                <li className="layout-row">
                  <JobStatusBox
                    status={data.status}
                    filePath={data.file_path}
                    startFrame={data.start_frame}
                    endFrame={data.end_frame}
                    timeElapsed={data.time_elapsed}
                    timeAvg={data.time_avg}
                    timeRemaining={data.time_remaining}
                    progress={data.progress}
                  />
                </li>
                <li className="layout-row">
                    <button className="sm-button" onClick={this.startJob}>Start</button>
                    <button className="sm-button" onClick={this.stopJob}>Stop</button>
                    <button className="sm-button" onClick={this.enqueueJob}>Enqueue</button>
                    <button className="sm-button" onClick={this.deleteJob}>Delete</button>
                </li>
                <li className="layout-row">
                  {Object.keys(data.node_status).map(node => this.renderNodeBox(node, data.node_status[node]))}
                </li>
              </ul>
            </div>
          </li>
        </ul>
      </div>
    )
  }
}


export default JobStatusPane;
