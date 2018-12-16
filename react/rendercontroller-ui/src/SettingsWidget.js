import React, { Component } from 'react';
import './SettingsWidget.css'
import CheckBox from './CheckBox'

/**
 * Displays settings in a popup overlay and closes when clicked outside.
 * @param {boolean} autostart - State of autostart setting
 * @param {function} onClose - Action to take when window is closed.
 * @param {function} toggleAutostart - Callback to flip state of autostart
 */
class SettingsWidget extends Component {
  constructor(props) {
    super(props);
    this.node = React.createRef();
    this.handleClick = this.handleClick.bind(this);
  }

  componentWillMount() {
    document.addEventListener('mousedown', this.handleClick, false);
  }

  componentWillUnmount() {
    document.removeEventListener('mousedown', this.handleClick, false);
  }

  handleClick(event) {
    if (this.node.current.contains(event.target)){
      // Ingore clicks inside this component
      return;
    }
    this.props.onClose();
  }

  render() {
    return (
      <div className="settings-container" ref={this.node}>
        <div className="settings-inner">
          <CheckBox
            label="Start renders automatically"
            checked={this.props.autostart}
            onChange={this.props.toggleAutostart}
            className="settings-field"
          />
        </div>
      </div>
    )
  }
}

export default SettingsWidget;
