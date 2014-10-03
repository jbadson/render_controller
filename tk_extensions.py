import tkinter as tk
import tkinter.ttk as ttk

'''Some customized tkinter and ttk widget subclasses. Still very
experimental. Written for Python 3.4'''

class Progressbar(tk.Canvas):
    '''Horizontal progress bar widget that can be configured with different
    colors.

    If a large number of these are used in a single window, it may be helpful to
    manually call the update_idletasks() method on the window to force updates.'''

    BGCOLOR = '#%02x%02x%02x' %(212, 212, 212)
    OUTLINECOLOR = '#%02x%02x%02x' %(122, 122, 122)
    BLUE = '#1E90FF'
    GREEN = '#00E600'
    RED = '#F01E1E'
    GOLD = '#F5DC00'
    GRAY = '#646464'
    PURPLE = '#9932CC'

    def __init__(self, master=None, length=100, color='blue', *args, **kwargs):
        self.barlength = length - 5 #length of inner bar adjusted for padding
        self.height=17
        tk.Canvas.__init__(
            self, master=master, height=20, width=length, 
            highlightthickness=0, *args, **kwargs
            )
        base = self._base_rect(
            length=length, height=self.height, 
            outline=Progressbar.OUTLINECOLOR, fill=Progressbar.BGCOLOR
            )
        #draw prog bar
        self.pbar = self._innerbar(0)

    def _base_rect(self, length, height, outline, fill):
        '''Basic rectangle shape.'''
        pad = 5 #prevents edges of canvas from clipping bar
        top = 5 #top offset
        rnd = 1 #pixels of corner rounding
        l = length - pad #width
        #prevent inner bar from entering into left pad space
        if l < pad:
            return 
        h = height 
        return (
            self.create_polygon(
                pad, top + rnd, #top-left
                pad + rnd, top,

                l - rnd, top, #top-right
                l, top + rnd,

                l, h - rnd, #bottom-right
                l - rnd, h,

                pad + rnd, h, #bottom-left
                pad, h - rnd,
                joinstyle=tk.ROUND, outline=outline, fill=fill)
            )

    def _innerbar(self, length, color=None):
        if not color:
            color = Progressbar.BLUE
        if length < 6:
            length = 6
        #if length < 6:
        #    return (
        #        self.create_rectangle(6,6,6,self.height, fill='', outline='')
        #        )
        return (
            self.create_rectangle(6,6, length,self.height, fill=color, 
                                  outline='')
            )

    def set(self, percent=0, color=None):
        '''Sets progress bar position and bar colorscheme.'''
        if percent < 0 or percent > 100:
            return
        newlength = self.barlength * percent/100
        if newlength < 6:
            newlength = 6
        #self.delete(self.pbar)
        #self.pbar = self._innerbar(newlength, color)
        self.coords(self.pbar, 6,6,newlength,self.height)
        if color:
            self.itemconfig(self.pbar, fill=color)


class RectButton(tk.Frame):
    '''Subclass of tkinter Frame that looks and behaves (kind of) like a 
    rectangular button in the OSX Aqua interface.'''
    BGCOLOR = '#%02x%02x%02x' % (235, 235, 235)
    HIGHLIGHT = '#%02x%02x%02x' % (74, 139, 222)

    def __init__(self, master, text='Button', command=None, bg=BGCOLOR):
        self.bgcolor = bg
        self.command = command
        tk.LabelFrame.__init__(self, master, borderwidth=1, relief=tk.GROOVE, 
                               bg=self.bgcolor)
        self.lbl = tk.Label(self, text=text, bg=self.bgcolor)
        self.lbl.pack(expand=True, fill=tk.BOTH, padx=3)
        self.bind('<Button-1>', self._select)
        self.lbl.bind('<Button-1>', self._select)
        self.bind('<ButtonRelease-1>', self._execute)
        self.lbl.bind('<ButtonRelease-1>', self._execute)
        self.bind('<Leave>', self._deselect)
        self.lbl.bind('<Leave>', self._deselect)

    def _select(self, event=None):
        '''Changes the background color to the highlight color'''
        self.selected = True
        self.config(bg=self.HIGHLIGHT)
        self.lbl.config(bg=self.HIGHLIGHT)
        self.update_idletasks()

    def _deselect(self, event=None):
        self.selected = False
        self.config(bg=self.bgcolor)
        self.lbl.config(bg=self.bgcolor)
        return

    def _execute(self, event=None):
        '''Returns the button bgcolor to it's original state and executes
        the button's command attribute.'''
        if self.command and self.selected:
            self.command()
        self._deselect()


class MarkedScale(ttk.Frame):
    '''Version of ttk Scale that includes tickmarks below the
    horizontal scale bar.'''
    def __init__(self, master=None, start=0, end=10, length=100, variable=None, 
                 command=None, font='TkSmallCaptionFont'):
        self.start = start
        self.end = end
        self.length = length
        self.var = variable #must be a tkinter variable
        self.font = font
        ttk.Frame.__init__(self, master=master)
        self.scale = ttk.Scale(self, from_=start, to=end, variable=self.var, 
                               command=command)
        self.scale.pack(expand=True, fill=tk.X)
        self.ticks().pack(padx=4, expand=True, fill=tk.X)

    def ticks(self):
        tickframe = ttk.Frame(self)
        ttk.Label(tickframe, text=self.start, font=self.font).pack(side=tk.LEFT)
        for i in range(self.start + 1, self.end):
            ttk.Label(tickframe, text='.', font=self.font
                ).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Label(tickframe, text=self.end, font=self.font).pack(side=tk.RIGHT)
        return tickframe

    def set(self, value):
        '''Sets the value of the progress bar.'''
        self.scale.set(value)
            



if __name__ == '__main__':
    '''Show a demo of widgets'''

    root = tk.Tk()
    root.geometry=('640x480')
    a = MarkedScale(root, start=10, end=100)
    a.pack(padx=100, pady=100)
    root.mainloop()
