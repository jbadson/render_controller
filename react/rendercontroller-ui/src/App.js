import React, { Component } from 'react';
import axios from 'axios';
import './App.css';
import JobInput from './JobInput';
import CheckBox from './CheckBox';

/* TODO:
√- Get REST API completely working -- will make remaining UI development much easier
√- Select active jobs from queue
√- New job input (new pane or page?)
- Make all buttons work
  √Start
  √Stop -- How to handle kill/no? Can't do popups
  √Resume -- How to handle  start now/later
  √Delete -- How to do confirmation?
  Autostart (make a dropdown or something so we only query state when needed)
- Disable (preferably gray out or hide) buttons in irrelevant contexts:
  Enqueue when state != stopped
  Start when state == running
- Tooltips for buttons, especially start, stop, enqueue
√- Node enable/disable checkboxes
- Color-coded progress bars and queue blocks
- Finish styling
√- Deal with Windows path conversion
    -> Alternatively could allow uploading of project directory
       (might be more complex to make sure paths are all relative)
    -> Or can have custom thing in UI to convert windows paths to linux
    -> Finally, can just make them manually enter the path
- Review all FIXMEs and TODOs
- Figure out how to package this for distribution
*/

const POLL_INTERVAL = 1000; // Milliseconds
const API_CONNECT = "http://localhost:2020";


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


function ProgressFill(props) {
  const className = props.className || "progress-fill";
  return <div className={className} style={{ width: `${props.percent}%`}} />
}


function ProgressBar(props) {
  return (
    <div className="progress-bar">
      <ProgressFill className={props.className} percent={props.percent} />
    </div>
  )
}

function NodeProgressBar(props) {
  return (
    <div className="node-progress-bar">
      <ProgressFill className={props.className} percent={props.percent} />
    </div>
  )
}


class StatusBox extends Component {
  /* Displays the overall status of a render job */
  startJob() {
    axios.post(API_CONNECT + "/job/start/" + this.props.id)
      .then(
        (result) => {console.log(result)},
        (error) => {console.error(error.message)}
      );
  }

  stopJob() {
    axios.post(API_CONNECT + "/job/stop/" + this.props.id)
    .then(
      //FIXME: Add confirmation of some kind
      (result) => {console.log(result)},
      (error) => {console.error(error.message)}
    );
  }

  enqueueJob() {
    axios.post(API_CONNECT + "/job/enqueue/" + this.props.id)
    .then(
      //FIXME: Add note about starting job manually
      (result) => {console.log(result)},
      (error) => {console.error(error.message)}
    );
  }

  deleteJob() {
    axios.post(API_CONNECT + "/job/delete/" + this.props.id)
    .then(
      //FIXME: Add confirmation and warning if job is not stopped
      (result) => {console.log(result)},
      (error) => {console.error(error.message)}
    );
  }

  render() {
    let progBarClass = "progress-fill";
    if (this.props.status === "Stopped") {
      progBarClass += "-stopped";
    } else if (this.props.status === "Finished") {
      progBarClass += "-finished"
    }

    return (
      <div className="status-box">
        <ul>
          <li className="layout-row">
            <p className="left">Status: {this.props.status}</p>
            <p className="right">End frame: {this.props.endFrame}</p>
            <p className="right">Start frame: {this.props.startFrame}</p>
          </li>
          <li className="layout-row">
            <p className="left">Project file: {this.props.filePath}</p>
          </li>
          <li className="layout-row">
            <div className="progress-container">
              <ProgressBar className={progBarClass} percent={this.props.progress.toFixed(1)} />
              <div className="progress-number">{this.props.progress.toFixed(1)} %</div>
            </div>
          </li>
          <li className="layout-row">
            <p className="left">Time elapsed: {fmtTime(this.props.timeElapsed)}</p>
            <p className="right">Time remaining: {fmtTime(this.props.timeRemaining)}</p>
          </li>
          <li className="layout-row">
            <button onClick={() => this.startJob()}>Start</button>
            <button onClick={() => this.stopJob()}>Stop</button>
            <button onClick={() => this.enqueueJob()}>Enqueue</button>
            <button onClick={() => this.deleteJob()}>Delete</button>
            <p className="right">Avg. time/frame: {fmtTime(this.props.timeAvg)}</p>
          </li>
        </ul>
      </div>
    )
  }
}


class NodeStatusBox extends Component {
  /* Displays the status of a render node */
  handleToggle() {
    let action = "enable";
    if (this.props.isEnabled) {
      action = "disable";
    }
    axios.get(API_CONNECT + "/node/" + action + "/" + this.props.name + "/" + this.props.jobId)
      .then(
        (result) => {console.log(result)},
        (error) => {console.error(error.message)}
      );
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
            <div className="node-progress-container">
              <NodeProgressBar percent={this.props.progress} />
            </div>
          </li>
          <li className="layout-row">
            <p className="left">Frame: {this.props.frame}</p>
            <p className="right">{this.props.progress.toFixed(0)} % Complete</p>
          </li>
        </ul>
      </div>
    )
  }
}

class QueueStatusBox extends Component {
  /* Displays summary of status for a render job. */
  render() {
    let className = "queue-status-box";
    if (this.props.isSelected) {
      className += "-active";
    }

    let progBarClass = "progress-fill";
    if (this.props.status === "Stopped") {
      progBarClass += "-stopped";
    } else if (this.props.status === "Finished") {
      progBarClass += "-finished"
    }

    return (
      <div
        className={className}
        key={this.props.fileName}
        onClick={this.props.onClick}
      >
        <ul>
          <li className="layout-row">
            <div className="left">{this.props.fileName}</div>
            <div className="right">{this.props.status}</div>
          </li>
          <li className="layout-row">
            <div className="node-progress-container">
              <NodeProgressBar className={progBarClass} percent={this.props.progress} />
            </div>
          </li>
          <li className="layout-row">
            <p className="left">{this.props.progress.toFixed(0)} % Complete</p>
            <p className="right">{this.props.timeRemaining} Remaining</p>
          </li>
        </ul>
      </div>
    )
  }
}


class JobStatusPane extends Component {
  /* Contains a StatusBox and NodeStatusBoxes for a job */
  constructor(props) {
    super(props)
    this.state = {
      data: {},
    }
  }

  getUpdate() {
    axios.get(API_CONNECT + "/job/status/" + this.props.id)
      .then(
        (result) => {
          this.setState({
            data: result.data,
          });
        },
        (error) => {
          this.setState({
            error: error,
        });
      }
    )
  }

  componentDidMount() {
    this.getUpdate()
    this.interval = setInterval(() => this.getUpdate(), POLL_INTERVAL);
  }

  componentWillUnmount() {
    clearInterval(this.interval);
  }

  renderMainBox() {
    const data = this.state.data;
    return (
      <StatusBox
        id={data.id}
        status={data.status}
        filePath={data.file_path}
        startFrame={data.start_frame}
        endFrame={data.end_frame}
        timeElapsed={data.time_elapsed}
        timeAvg={data.time_avg}
        timeRemaining={data.time_remaining}
        progress={data.progress}
      />
    )
  }

  renderNodeBox(name, nodeStatus) {
    return (
      <NodeStatusBox
        key={name}
        name={name}
        jobId={this.props.id}
        isRendering={nodeStatus.rendering}
        isEnabled={nodeStatus.enabled}
        frame={nodeStatus.frame}
        progress={nodeStatus.progress}
      />
    )
  }

  renderPane() {
    return (
      <div>
        <ul>
          <li className="layout-row">
            {this.renderMainBox(this.state.data)}
          </li>
          <li className="layout-row">
            {Object.keys(this.state.data.node_status).map(node => this.renderNodeBox(node, this.state.data.node_status[node]))}
          </li>
        </ul>
      </div>
    )
  }

  render() {
    if (!this.state.data.node_status) {
      return <div>Loading...</div>
    }
    return this.renderPane()
  }
}

function getBasename(path) {
  const parts = path.split('/')
  return parts[parts.length - 1]
}

class App extends Component {
  constructor(props) {
    super(props)
    this.state = {
      data: {},
      error: null,
      selectedJob: null,
      showInputPane: false,
      renderNodes: [],
    }
  }

  getUpdate() {
    // Fetch data from server and update UI
    axios.get(API_CONNECT + "/job/summary")
      .then(
        (result) => {
          this.setState(state => {
            let selectedJob = state.selectedJob;
            if (!state.selectedJob) {
              selectedJob = result.data.jobs[0];
            }
            return {
            data: result.data,
            selectedJob: selectedJob,
          }});
        },
        (error) => {
          this.setState({
            error: error,
        });
      }
    )
  }

  getRenderNodes() {
    axios.get(API_CONNECT + "/node/list")
      .then(
        (result) => {
          let renderNodes = {}
          for (var i = 0; i < result.data.length; i++) {
            renderNodes[result.data[i]] = false;
          }
          return this.setState({renderNodes: renderNodes})},
        (error) => {console.log(error)}
      )
  }

  componentDidMount() {
    // Set interval to poll server for updates
    // Performance is bad especially if interval is short
    // Websockets would probably be even better
    this.getUpdate();
    this.getRenderNodes();
    this.interval = setInterval(() => this.getUpdate(), POLL_INTERVAL);
  }

  componentWillUnmount() {
    clearInterval(this.interval);
  }

  toggleInputPane() {
    this.setState(state => ({showInputPane: !state.showInputPane}))
  }

  renderQueueBox(job) {
    let selected = false;
    if (this.state.selectedJob && this.state.selectedJob.id === job.id) {
      selected = true;
    };
    return (
      <li className="layout-row" key={job.id}>
        <QueueStatusBox
          key={job.id}
          fileName={getBasename(job.file_path)}
          status={job.status}
          isSelected={selected}
          timeRemaining={job.time_remaining}
          progress={job.progress}
          onClick={() => this.setState({selectedJob: job})}
        />
    </li>
    )
  }

  renderStatusPane() {
    const job = this.state.selectedJob
    if (!job) {
      return <p>No job selected.</p>
    }
    return <JobStatusPane key={job.id} id={job.id} />
  }

  render() {
    const { data, error } = this.state;

    if (error) {
      return <div>Error {error.message}</div>
    } else if (!data.jobs) {
      //FIXME will be empty if server is idle. Handle correctly
      return <div>Error: No data to render</div>
    }
    // FIXME: App never unmounts even when status pane is hidden, so App's
    // update interval never stops.
    if (this.state.showInputPane) {
      console.log(this.state.renderNodes)
      return (
        <JobInput
          path="/"
          url={API_CONNECT}
          renderNodes={this.state.renderNodes}
          onClose={() => this.toggleInputPane()}
        />
      )
    }
    return (
      <div className="wrapper">
        <ul>
          <li className="layout-row">
            Queue
            <button onClick={() => this.toggleInputPane()} >New</button>
            <CheckBox label="Autostart" checked={data.autostart} onChange={() => alert('garble')}/>
            <h1>Stop fiddling with appearance and make work w/ existing script</h1>
          </li>
          <li className="layout-row">
            <div className="queue-pane">
              <ul>
                {data.jobs.map(job => this.renderQueueBox(job))}
              </ul>
            </div>
            <div className="status-pane">
              {this.renderStatusPane()}
            </div>
          </li>
        </ul>
      </div>
    )
  }
}


export default App;
//export default JobInput;
