from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, render_to_response
from django.template import RequestContext
from possem.twitter import tweet_post
from .models import Post, Note, Article, Reply
from .forms import ComposeForm

# Create your views here.

def frontpage ( request ) :
  return post_list( request )

def feed ( request ) :
  # Get page number
  try :
    page  = int( request.GET["page"] )
    start = ( page - 1 ) * 30
    end   = start + 30
  except :
    page  = 1
    start = 0
    end   = 30

  post_list = Note.objects.order_by( '-date_posted' )[start:end]
  
  last_page = len( post_list ) < 30

  return render_to_response( 'grmbl/post_list.html', { 'post_list' : post_list, 'page' : page, 'last_page' : last_page }, context_instance = RequestContext( request ) )

def articles ( request ) :
  # Get page number
  try :
    page  = int( request.GET["page"] )
    start = ( page - 1 ) * 10
    end   = start + 10
  except :
    page  = 1
    start = 0
    end   = 10

  post_list = Article.objects.order_by( '-date_posted' )[start:end]
  
  last_page = len( post_list ) < 10

  return render_to_response( 'grmbl/post_list.html', { 'post_list' : post_list, 'page' : page, 'last_page' : last_page }, context_instance = RequestContext( request ) )

def post_list ( request ) :
  # Get page number
  try :
    page  = int( request.GET["page"] )
    start = ( page - 1 ) * 15
    end   = start + 15
  except :
    page  = 1
    start = 0
    end   = 15

  # Get search tags
  try :
    tag   = request.GET["tag"]
    post_list = Post.objects.filter( tags__contains = tag ).order_by( '-date_posted' )[start:end]
  except :
    post_list = Post.objects.order_by( '-date_posted' )[start:end]
  
  last_page = len( post_list ) < 15

  return render_to_response( 'grmbl/post_list.html', { 'post_list' : post_list, 'page' : page, 'last_page' : last_page }, context_instance = RequestContext( request ) )

def post_detail ( request, pid ) :
  post = get_object_or_404( Post, pk = pid )

  return render_to_response( 'grmbl/post_detail.html', { 'post' : post, 'tags' : post.tags.split( " " ) }, context_instance = RequestContext( request ) )

def shortlink( request, pid ) :
  # Shortlinks should just redirect to the valid post
  return HttpResponseRedirect( '/posts/' + str( pid ) )

def compose ( request ) :
  if not request.user.is_authenticated or not request.user.is_staff :
    return HttpResponseForbidden()

  if request.method == "POST" :
    form = ComposeForm( request.POST )

    if form.is_valid() :
      title   = form.cleaned_data['title']
      content = form.cleaned_data['content']
      tags    = form.cleaned_data['tags']

      if title :
        new_article         = Article()
        new_article.title   = title
        new_article.content = content
        new_article.tags    = tags

        new_article.save()
        post = new_article
      else :
        if form.cleaned_data['reply_to'] :
          reply_to    = form.cleaned_data['reply_to']
          reply_name  = form.cleaned_data['reply_name']
          reply_prof  = form.cleaned_data['reply_prof']

          new_reply         = Reply()
          new_reply.content = content
          new_reply.tags    = tags

          new_reply.reply_url     = reply_to
          new_reply.display_name  = reply_name
          new_reply.profile       = reply_prof

          new_reply.save()
          post = new_reply
        else :
          new_note          = Note()
          new_note.content  = content
          new_note.tags     = tags

          new_note.save()
          post = new_note

      tweet_post( post )
      return HttpResponseRedirect( '/posts/' + str( post.pk ) )
  else :
    form = ComposeForm()

  return render_to_response( 'grmbl/compose.html', { 'form' : form }, context_instance = RequestContext( request ) )