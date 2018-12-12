import React, { Component } from 'react';
import './App.css';
import JobInput from './JobInput';
import QueuePane from './QueuePane';
import JobStatusPane from './JobStatus';

/* TODO:
- Settings popup/menu
  - Should show autostart status and modify, poll interval?
- Order queue boxes by queue position (or queue time)
- Disable (preferably gray out or hide) buttons in irrelevant contexts:
  Enqueue when state != stopped
  Start when state == running
- Tooltips for buttons, especially start, stop, enqueue
- Finish styling
- Review all FIXMEs and TODOs
- Figure out how to package this for distribution
*/

const POLL_INTERVAL = 1000; // Milliseconds
const API_CONNECT = "http://localhost:2020";


class App extends Component {
  constructor(props) {
    super(props);
    this.state = {
      selectedJob: null,
      showInputPane: false,
    }
    this.selectJob = this.selectJob.bind(this);
    this.toggleInputPane = this.toggleInputPane.bind(this);
  }

  selectJob(jobId) {
    this.setState({selectedJob: jobId})
  }

  toggleInputPane() {
    this.setState(state => ({showInputPane: !state.showInputPane}))
  }

  renderContentPane() {
    if (this.state.showInputPane) {
      return (
        <JobInput
          path="/"
          url={API_CONNECT}
          renderNodes={this.state.renderNodes}
          onClose={this.toggleInputPane}
        />
      )
    } else if (this.state.selectedJob) {
      // FIXME: Select correct default and don't break if queue is empty
      return (
        <JobStatusPane
          jobId={this.state.selectedJob}
          url={API_CONNECT}
          pollInterval={POLL_INTERVAL}
        />
      )
    }
    return <p>No job selected</p>
  }

  render() {
    return (
      <ul>
        <li className="layout-row">
          <button className="button-left" onClick={this.toggleInputPane}>New</button>
          <button className="button-right">Settings</button>
        </li>
        <li className="layout-row">
          <div className="sidebar">
            <QueuePane
              url={API_CONNECT}
              pollInterval={POLL_INTERVAL}
              onJobClick={this.selectJob}
              selectedJob={this.state.selectedJob}
            />
          </div>
          <div className="content-pane">
            {this.renderContentPane()}
          </div>
        </li>
      </ul>
    )
  }
}


export default App;
