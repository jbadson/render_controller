import React, { Component } from 'react';
import axios from 'axios';
import './App.css';

/* TODO:
- Get REST API completely working -- will make remaining UI development much easier
  Translation layer done. Need to finish methods in server to talk to it.
√- Select active jobs from queue
- New job input (new pane or page?)
- Make all buttons work
  Edit -- Could remove this and just make people put in new job
  √Start
  Stop -- How to handle kill/no? Can't do popups
  Resume -- How to handle  start now/later
  Delete -- How to do confirmation?
√- Node enable/disable checkboxes
- Finish styling buttons
- Deal with Windows path conversion
    -> Alternatively could allow uploading of project directory
       (might be more complex to make sure paths are all relative)
    -> Or can have custom thing in UI to convert windows paths to linux
    -> Finally, can just make them manually enter the path
- Figure out how to package this for distribution
*/

const POLL_INTERVAL = 1000; // Milliseconds
const API_CONNECT = "http://localhost:2020";

class ToggleSwitch extends Component {
  render() {
    return (
      <label>
        {this.props.label}
        <input
          type="checkbox"
          checked={this.props.checked}
          onChange={this.props.onChange}
        />
      </label>
    )
  }
}


function ProgressFill(props) {
  return <div className="progress-fill" style={{ width: `${props.percent}%`}} />
}

class ProgressBar extends Component {
  render() {
    return (
      <div className="progress-bar">
        <ProgressFill percent={this.props.percent} />
      </div>
    )
  }
}

class NodeProgressBar extends Component {
  render() {
    return (
      <div className="node-progress-bar">
        <ProgressFill percent={this.props.percent} />
      </div>
    )
  }
}


class StatusBox extends Component {
  /* Displays the overall status of a render job */
  startJob() {
    axios.post(API_CONNECT + "/start/" + this.props.id)
  }
  render() {
    return (
      <div className="status-box">
        <ul>
          <li className="status-row">
            <p className="left">Status: {this.props.status}</p>
            <p className="right">End frame: {this.props.endFrame}</p>
            <p className="right">Start frame: {this.props.startFrame}</p>
          </li>
          <li className="status-row">
            <p className="left">Project file: {this.props.filePath}</p>
          </li>
          <li className="status-row">
            <div className="progress-container">
              <ProgressBar percent={this.props.progress} />
              <div className="progress-number">{this.props.progress} %</div>
            </div>
          </li>
          <li className="status-row">
            <p className="left">Time elapsed: {this.props.timeElapsed}</p>
            <p className="right">Time remaining: {this.props.timeRemaining}</p>
          </li>
          <li className="status-row">
            <button onClick={() => this.editJob()}>Edit</button>
            <button onClick={() => this.startJob()}>Start</button>
            <button onClick={() => this.stopJob()}>Stop</button>
            <button onClick={() => this.resumeJob()}>Resume</button>
            <button onClick={() => this.deleteJob()}>Delete</button>
            <p className="right">Avg. time/frame: {this.props.timeAvg}</p>
          </li>
        </ul>
      </div>
    )
  }
}


class NodeStatusBox extends Component {
  /* Displays the status of a render node */
  handleToggle() {
    axios.post(API_CONNECT + "/rendernode/" + this.props.name + "/" + this.props.jobId + "/toggle")
  }

  renderCheckbox() {
    return (
      <label>
        <form>
          <input
            type="checkbox"
            className="right"
            value={this.props.name}
            checked={this.props.isEnabled}
            onChange={() => this.handleToggle()}
          />
        Enabled:&nbsp;
        </form>
      </label>
    )
  }

  render() {
    return (
      <div className="node-status-box" key={this.props.name}>
        <ul>
          <li className="status-row">
            <div className="left">{this.props.name}</div>
            <div className="right">{this.renderCheckbox()}</div>
          </li>
          <li className="status-row">
            <div className="node-progress-container">
              <NodeProgressBar percent={this.props.progress} />
            </div>
          </li>
          <li className="status-row">
            <p className="left">Frame: {this.props.frame}</p>
            <p className="right">{this.props.progress} % Complete</p>
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
    return (
      <div
        className={className}
        key={this.props.fileName}
        onClick={this.props.onClick}
      >
        <ul>
          <li className="status-row">
            <div className="left">{this.props.fileName}</div>
            <div className="right">{this.props.status}</div>
          </li>
          <li className="status-row">
            <div className="node-progress-container">
              <NodeProgressBar percent={this.props.progress} />
            </div>
          </li>
          <li className="status-row">
            <p className="left">{this.props.progress} % Complete</p>
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
    axios.get(API_CONNECT + "/job/" + this.props.id)
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
        key={data.id}
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

  renderNodeBox(nodeStatus) {
    return (
      <NodeStatusBox
        key={this.props.id + nodeStatus.name}
        jobId={this.props.id}
        isRendering={nodeStatus.is_rendering}
        isEnabled={nodeStatus.is_enabled}
        name={nodeStatus.name}
        frame={nodeStatus.frame}
        progress={nodeStatus.progress}
      />
    )
  }

  renderPane() {
    return (
      <div>
        <ul>
          <li className="status-row">
            {this.renderMainBox(this.state.data)}
          </li>
          <li className="status-row">
            {this.state.data.node_status.map(nodeStatus => this.renderNodeBox(nodeStatus))}
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
  var parts = path.split('/')
  return parts[parts.length - 1]
}

class App extends Component {
  constructor(props) {
    super(props)
    this.state = {
      data: {},
      error: null,
      selectedJob: null,
    }
  }

  getUpdate() {
    // Fetch data from server and update UI
    axios.get(API_CONNECT + "/status")
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
    // Set interval to poll server for updates
    // Performance is bad especially if interval is short
    // Websockets would probably be even better
    this.getUpdate()
    this.interval = setInterval(() => this.getUpdate(), POLL_INTERVAL);
  }

  componentWillUnmount() {
    clearInterval(this.interval);
  }

  renderQueueBox(job) {
    var selected = false;
    if (this.state.selectedJob && this.state.selectedJob.id === job.id) {
      selected = true;
    };
    return (
      <li className="status-row">
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

    return (
      <div className="wrapper">
        <ul>
          <li className="status-row">
            Queue
            <button>New</button>
            <ToggleSwitch label="Autostart" checked={data.autostart} onChange={() => alert('garble')}/>
            <h1>Stop fiddling with appearance and make work w/ existing script</h1>
          </li>
          <li className="status-row">
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
