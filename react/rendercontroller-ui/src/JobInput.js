import React, { Component } from "react";
import "./JobInput.css";
import FileBrowser from './FileBrowser';

/**
 * Displays FileBrowser in a popup overlay.
 */
function BrowserPopup(props) {
  return (
    <div className="browser-overlay" >
      <div className="browser-inner">
        <ul>
          <li className="layout-row">
            <p className="right" onClick={props.onClose}>X</p>
          </li>
          <li className="layout-row">
            <FileBrowser
              url={props.url}
              path={props.path}
              onFileClick={props.onFileClick}
            />
          </li>
        </ul>
      </div>
    </div>
  )
}


/**
 * Number input form that changes CSS className if value contains a non-digit.
 * @param {int} value: Contents of input field.
 * @param {function} onChange - Callback on input change.
 */
class NumberInput extends Component {
  constructor(props) {
    super(props);
    this.classNameOk = "number-input";
    this.classNameBad = "number-input-bad";
    this.state = {
      className: this.classNameOk
    }
    this.handleChange = this.handleChange.bind(this);
  }

  handleChange(event) {
    let className = this.classNameOk;
    if (isNaN(event.target.value)) {
      className = this.classNameBad;
    }
    this.setState({
      className: className,
    });
    this.props.onChange(event);
  }

  render() {
    return (
      <label>
        Input:
        <input type="text"
          className={this.state.className}
          value={this.props.value}
          onChange={this.handleChange}
        />
      </label>
    )
  }
}


/**
 * Job input widget.
 * @param {function} onSubmit - Called when input is submitted.
 * @param {str} url - URL of API
 */
class JobInput extends Component {
  constructor(props) {
    super(props);
    this.state = {
      path: props.path,
      startFrame: props.startFrame ? undefined: '',
      endFrame: props.endFrame ? undefined: '',
      renderEngine: props.renderEngine,
      renderNodes: props.renderNodes,
      showBrowser: false,
    }
    this.toggleBrowser = this.toggleBrowser.bind(this);
    this.setPath = this.setPath.bind(this);
    this.handlePathChange = this.handlePathChange.bind(this);
    this.handleStartChange = this.handleStartChange.bind(this);
    this.handleEndChange = this.handleEndChange.bind(this);
  }

  toggleBrowser() {
    this.setState(state => ({showBrowser: !state.showBrowser}));
  }

  setPath(path) {
    this.setState({
      path: path,
      showBrowser: false,
    });
  }

  handlePathChange(event) {
    this.setState({path: event.target.value})
  }

  handleStartChange(event) {
    //FIXME complain if not number
    this.setState({startFrame: event.target.value})
  }

  handleEndChange(event) {
    //FIXME complain if not number
    this.setState({endFrame: event.target.value})
  }

  render() {
    return (
      <div className="input-container">
        {this.state.showBrowser &&
          <BrowserPopup
            url={this.props.url}
            path={this.props.path}
            onClose={this.toggleBrowser}
            onFileClick={this.setPath}
          />
        }
        <form>
          <ul>
            <li className="layout-row">
              <label>
                Path:
                <input type="text" value={this.state.path} onChange={this.handlePathChange} />
                <input type="button" value="Browse" onClick={this.toggleBrowser} />
              </label>
            </li>
            <li className="layout-row">
              <NumberInput value={this.state.startFrame} onChange={this.handleStartChange} />
              <NumberInput value={this.state.endFrame} onChange={this.handleEndChange} />
            </li>
            <li className="layout-row">Render nodes</li>
            <li className="layout-row">OK, Cancel</li>
            <li className="layout-row">Check:<br />Path: "{this.state.path}"<br />Start: {this.state.startFrame} End: {this.state.endFrame}</li>
          </ul>
        </form>
      </div>
    )
  }
}



class Wrapper extends Component {
  render() {
    return <JobInput path="/" url={"http://localhost:2020"+ "/browse"} />
  }
}

export default Wrapper;
