import React, { Component } from 'react';
import './JobStatus.css';
import axios from 'axios';
import ProgressBar from './ProgressBar';
import CheckBox from './CheckBox';
import JobInput from './JobInput';
import { fmtTime, getBasename } from './util';

/**
 * Render node status widget.
 * @prop {string} name - Node Name
 * @prop {string} jobId - ID of job this node is rendering
 * @prop {boolean} isEnabled - Is node enabled for rendering?
 * @prop {int} frame - Fram node is currently rendering
 * @prop {float} progress - Percent frame complete
 */
class NodeStatusBox extends Component {
  handleToggle() {
    let action = "enable";
    if (this.props.isEnabled) {
      action = "disable";
    }
    axios.get(process.env.REACT_APP_BACKEND_API + "/node/" + action + "/" + this.props.name + "/" + this.props.jobId)
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
 * @prop {string} filePath - Path to project file
 * @prop {string} status - Job status
 * @prop {float} progress - Percent complete
 * @prop {float} timeRemaining - Time until render complete (sec)
 * @prop {float} timeElapsed - Rendering time (sec)
 */
function JobStatusBox(props) {
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
 * @prop {string} jobId - ID of render job
 * @prop {function} onDelete - Action to take after job is deleted.
 */
class JobStatusPane extends Component {
  constructor(props) {
    super(props)
    this.state = {
      data: null,
      error: null,
      showInputPane: false,
    }
    this.startJob = this.startJob.bind(this);
    this.stopJob = this.stopJob.bind(this);
    this.enqueueJob = this.enqueueJob.bind(this);
    this.deleteJob = this.deleteJob.bind(this);
    this.reRenderJob = this.reRenderJob.bind(this);
    this.toggleInputPane = this.toggleInputPane.bind(this);
  }

  startJob() {
    axios.post(process.env.REACT_APP_BACKEND_API + "/job/start/" + this.props.jobId)
      .then(
        (result) => {console.log(result)},
        (error) => {console.error(error.message)}
      );
  }

  stopJob() {
    axios.post(process.env.REACT_APP_BACKEND_API + "/job/stop/" + this.props.jobId)
    .then(
      (result) => {console.log(result)},
      (error) => {console.error(error.message)}
    );
  }

  enqueueJob() {
    axios.post(process.env.REACT_APP_BACKEND_API + "/job/reset_status/" + this.props.jobId)
    .then(
      (result) => {console.log(result)},
      (error) => {console.error(error.message)}
    );
  }

  deleteJob() {
    axios.post(process.env.REACT_APP_BACKEND_API + "/job/delete/" + this.props.jobId)
    .then(
      (result) => {console.log(result)},
      (error) => {console.error(error.message)}
    ).then(this.props.onDelete());
  }

  reRenderJob() {
    this.toggleInputPane();
  }

  toggleInputPane() {
    this.setState(state => ({showInputPane: !state.showInputPane}));
  }

  getUpdate() {
    axios.get(process.env.REACT_APP_BACKEND_API + "/job/info/" + this.props.jobId)
      .then(result => {
        this.setState({data: result.data});
        },
        error => {this.setState({error: error});
      }
    )
  }

  componentDidMount() {
    this.getUpdate()
    this.interval = setInterval(() => this.getUpdate(), process.env.REACT_APP_POLL_INTERVAL);
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
        isRendering={nodeStatus.rendering}
        isEnabled={nodeStatus.enabled}
        frame={nodeStatus.frame}
        progress={nodeStatus.progress}
      />
    )
  }

  getNodesEnabled() {
    const { node_status } = this.state.data;
    const nodesEnabled = [];
    Object.entries(node_status).forEach(([key, val]) => { if (val.enabled) { nodesEnabled.push(key)}});
    return nodesEnabled;
  }

  render() {
    const { data, error, showInputPane } = this.state;
    if (error) {
      return <p>Error: {error.message}</p>
    } else if (!data) {
      return <p>No data to display</p>
    }
    if (showInputPane) {
      return (
        <JobInput
          path={data.path}
          startFrame={data.start_frame}
          endFrame={data.end_frame}
          renderNodes={Object.keys(data.node_status)}
          nodesEnabled={this.getNodesEnabled()}
          onClose={this.toggleInputPane}
        />
      )
    } else {
      return (
        <div className="jsp-container">
          <ul>
            <li className="jsp-row">
              <div className="jsp-header">{getBasename(data.path)}</div>
            </li>
            <li className="jsp-row">
              <div className="jsp-inner">
                <ul>
                  <li className="layout-row">
                    <JobStatusBox
                      status={data.status}
                      filePath={data.path}
                      startFrame={data.start_frame}
                      endFrame={data.end_frame}
                      timeElapsed={data.time_elapsed}
                      timeAvg={data.time_avg_per_frame}
                      timeRemaining={data.time_remaining}
                      progress={data.progress}
                    />
                  </li>
                  <li className="layout-row">
                      <button
                        className="sm-button tooltip"
                        help-text="Start the render."
                        disabled={(data.status === 'Waiting' || data.status === 'Stopped') ? false : true}
                        onClick={this.startJob}>
                          Start
                      </button>
                      <button
                        className="sm-button tooltip"
                        help-text="Stop the render.  Stopped jobs will not be re-started automatically."
                        disabled={data.status === 'Rendering' ? false : true}
                        onClick={this.stopJob}>
                          Stop
                      </button>
                      <button
                        className="sm-button tooltip"
                        help-text="Change stopped job status to 'Waiting' so it can be started automatically."
                        disabled={data.status === 'Stopped' ? false : true}
                        onClick={this.enqueueJob}>
                          Return to Queue
                      </button>
                      <button
                        className="sm-button tooltip"
                        help-text="Create a new job based on this one. You will be able to modify the settings."
                        disabled={false}
                        onClick={this.reRenderJob}>
                          Duplicate
                      </button>
                      <button
                        className="sm-button tooltip"
                        help-text="Delete this job.  If job is currently rendering, you must stop it first."
                        disabled={data.status !== 'Rendering' ? false : true}
                        onClick={this.deleteJob}>
                          Delete
                      </button>
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
}


export default JobStatusPane;
